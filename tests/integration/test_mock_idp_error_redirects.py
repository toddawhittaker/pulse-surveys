"""How this provider says no, and where it says it — ticket E0-30, item 1.

E0-16 built every refusal as a 400 page. RFC 6749 §4.1.2.1 says that once the
`client_id` and the `redirect_uri` have validated, a refusal is **added to the
redirection URI's query** and the browser is sent there carrying `error`,
`error_description` and the `state` that arrived. E0-30 makes that change, and
this module is the battery for it.

**Why the transport matters when the verdict does not change.** E1's
`/auth/oidc/callback` has an error branch — parse `error`, match the returned
`state`, consume the pending login — and against a provider that answers pages
that branch is unreachable, so E1 ships it untested or does not ship it. The
case that will actually occur in use is a person who does not complete the
login, which arrives as `access_denied` by redirect. Nothing in this repository
can produce that shape today.

**Nothing here changes what is refused.** Every request below is one E0-16
already turned away, and it is turned away here for the same stated reason;
what is asserted is where the refusal is delivered and which §4.1.2.1 code
names it. The verdict half is asserted next door, in
`test_mock_idp_authorization_code_flow.py`, and that module keeps saying it.

**The line this module is really about is where the two behaviours divide.**
A refusal delivered before the redirect target has been validated is an open
redirector: the provider is then a service that will send a browser, with
parameters, to whatever address the request named. So the pre-validation
refusals — an unknown `client_id`, an unregistered `redirect_uri`, and a
duplicated one of either — must stay pages, and the test that matters most here
is the near miss:
`test_an_unregistered_redirect_uri_with_a_second_defect_produces_a_page_and_no_redirect`.
It sends a request that is wrong on *both* sides of the line, and a
implementation that computes the error before it checks the address answers it
with a redirect to the attacker's URI. Every other test in this file would stay
green against that implementation.

**Each page assertion carries its live control, or names the test that is one.**
"This refusal did not redirect" is satisfied perfectly by the provider as it
stands today, which redirects nothing at all — `docs/MISTAKES.md` entry 3. The
near-miss test therefore asserts *both* halves in one run: the same defect with
the registered URI redirects, and with the unregistered URI it does not. The
other page tests rest on the redirect tests in this same module failing loudly
if the provider ever went back to answering everything with a page, and say so.

**The parameters are sent as a list of pairs**, through the raw client rather
than through `MockIdentityProvider.begin`, for two reasons. A duplicated
parameter cannot be expressed as a mapping at all, which is the whole of the
duplicate-parameter split this ticket draws (ADR 0062 rule 3). And `begin`
follows the provider's own redirects to find a login form; what is under test
here *is* the redirect, so it is read where it arrives rather than followed.

**Two later sections came out of E0-30's second review round**, and both are
about what the redirect hands the client rather than about where it goes.
`error_description` may carry only the characters RFC 6749 Appendix A allows in
one, however the request was spelled — otherwise the caller picks the bytes the
client receives. And a `state` of nothing but spaces is refused for being absent
and must therefore not come back, which is one rule with a near miss beside it:
a `state` with real content and spaces around it is still echoed exactly.
The third finding of that round is registration-time and lives in
`tests/unit/test_mock_idp_service.py`, beside the `code` and `state` rules it
extends.

**What could not be tested here, said plainly rather than left to be inferred.**
`app/flow.py`'s `sign_in` refuses two things — a subject it does not know, and a
seeded person whose assignments do not open this door — and only the first is
reachable from outside. Every person in `mock-idp/app/seed.py` holds at least
one web-door assignment, so no request can make the second refusal fire, and a
launch-only subject submitted to the form is an unknown subject. The tests below
send both shapes and assert the same outcome for each; the second is a near
neighbour rather than the case itself, and it is flagged as one. Making it
reachable would mean seeding an instructor-only person on this door, which E0-16
forbids.
"""

from collections.abc import Sequence
from typing import Any
from urllib.parse import parse_qsl, urlsplit

import pytest

# `mock_idp` and `mock_idps` come from `tests/conftest.py` and are annotated
# `Any` for the reason the sibling flow module gives: a test module that imports
# its own `conftest` by name depends on where pytest happened to put `tests/` on
# `sys.path`, and an import error is not a red — it is a broken suite that
# reports nothing about the ticket.

# The error codes RFC 6749 §4.1.2.1 defines for the authorization endpoint,
# transcribed from the specification. Four of the seven are what this provider's
# refusals map onto (E0-30's scope names each raise site); the other three are
# here because the set is what makes the mapping a choice rather than a default —
# `server_error` is what a provider that had stopped distinguishing would answer.
INVALID_REQUEST = "invalid_request"
UNAUTHORIZED_CLIENT = "unauthorized_client"
ACCESS_DENIED = "access_denied"
UNSUPPORTED_RESPONSE_TYPE = "unsupported_response_type"
INVALID_SCOPE = "invalid_scope"
SERVER_ERROR = "server_error"
TEMPORARILY_UNAVAILABLE = "temporarily_unavailable"

AUTHORIZATION_ERROR_CODES = frozenset(
    {
        INVALID_REQUEST,
        UNAUTHORIZED_CLIENT,
        ACCESS_DENIED,
        UNSUPPORTED_RESPONSE_TYPE,
        INVALID_SCOPE,
        SERVER_ERROR,
        TEMPORARILY_UNAVAILABLE,
    }
)

# A redirect URI that is not the registered one and can never resolve: the
# `.invalid` top-level domain is reserved by RFC 2606. **This suite's choice** of
# value; that it must never be redirected to is RFC 6749 §4.1.2.1's. Written out
# here as well as in `test_mock_idp_authorization_code_flow.py` rather than
# shared: these two modules share code only through fixtures, and a constant
# whose whole content is "an address this provider never registered" says the
# same thing in both places without either depending on the other's spelling.
UNREGISTERED_REDIRECT_URI = "http://attacker.invalid/collect"

# A client this provider never registered, and a second value for the one it
# did. Both say where they came from, so one turning up in a log or a redirect
# is traceable to this file.
UNKNOWN_CLIENT_ID = "e0-30-unregistered-client"
FORGED_CLIENT_ID = "e0-30-forged-client"

# Values sent and then looked for coming back.
MARKER_STATE = "e0-30-state-marker"

# A `state` carrying the characters that mean something in a URL. RFC 6749
# §4.1.1 puts no grammar on `state` beyond the request encoding, so this is a
# value a client may legitimately choose, and it is the one that separates an
# echo from a re-encode: `&` and `=` split a query, the space and the `%` are
# what a second round of percent-encoding mangles. A client that reads this back
# and compares it to what it stored is doing the one check `state` exists for.
AWKWARD_STATE = "e0-30 state=one&two=three%2Ffour"

# A `state` with real content and whitespace on both ends. It is not blank, so
# nothing may treat it as absent, and RFC 6749 §4.1.2.1 requires the value the
# client sent back unchanged — including the padding. This is the near miss for
# the whitespace-only rule below: the tempting fix for "a blank `state` is
# missing" is to strip `state` and echo what is left, which silently rewrites
# this one and hands a client a value it cannot match.
PADDED_STATE = "  e0-30-padded-state  "

# The `state` values that carry no content at all, which the provider already
# refuses the request for. Two spellings of the same thing, because "blank"
# must not mean "exactly the one value that was measured".
BLANK_STATES = {"a single space": " ", "three spaces": "   "}

# A run of characters chosen so that a value reflected verbatim into
# `error_description` breaks RFC 6749 Appendix A's grammar for it. It carries:
#
#   - `"` (%x22) and `\` (%x5C), the two printable ASCII characters NQSCHAR
#     excludes, and the two that end a quoted string in a header, a JSON
#     document or a log line early;
#   - `§` (U+00A7), which is outside ASCII entirely;
#   - something HTML-shaped. Every character of `<script>alert(1)</script>` is
#     *inside* NQSCHAR, so this part is not what the assertion is about — it is
#     here because the value a provider reflects is chosen by whoever sends the
#     request, and the character bound is the only thing standing between that
#     and whatever reads the redirect next.
ADVERSARIAL_FRAGMENT = '"\\<script>alert(1)</script>§'

# The same fragment inside a `code_challenge` that is **43 characters long**, for
# the reason `MALFORMED_CODE_CHALLENGE` gives: 43 is the shortest a verifier may
# be, so a length check cannot be what refuses it.
POISONED_CODE_CHALLENGE = "a" * (43 - len(ADVERSARIAL_FRAGMENT)) + ADVERSARIAL_FRAGMENT

# Three post-validation refusals whose offending parameter carries the fragment,
# at three different raise sites. Three rather than one because the fix that is
# wrong is a sanitiser applied at the raise site the reproduction named; the fix
# that is right bounds the value where the redirect is built, and only that one
# holds for all three.
POISONED_REQUESTS = {
    "a poisoned response_type": {"response_type": f"token{ADVERSARIAL_FRAGMENT}"},
    "a poisoned scope token": {"scope": f"openid wibble{ADVERSARIAL_FRAGMENT}"},
    "a poisoned code challenge": {"code_challenge": POISONED_CODE_CHALLENGE},
}

# A `code_challenge` carrying one character outside RFC 7636 §4.1's alphabet and
# **43 characters long**. The length is why it is written out rather than typed
# at the call site: 43 is the minimum a verifier may be and the exact length of
# the base64url of a SHA-256 digest, so a length check cannot be what refuses it
# and the refusal is about the character — the same constant, and the same
# reasoning, as `NON_ASCII_PKCE_VALUE` in the flow module.
MALFORMED_CODE_CHALLENGE = "é" + "a" * 42

# The three parameters E0-30 maps to `invalid_request` when they are absent.
# `state` is in the list although its own refusal has a second rule (the redirect
# carries no `state` back), which is asserted separately below.
REQUIRED_PARAMETERS = ("state", "nonce", "code_challenge")

# The two malformed-PKCE shapes RFC 7636 §4.4.1 assigns `invalid_request`, as
# (what to override, with what). A wrong method and a challenge the alphabet
# rules out are different mistakes with one code, and E0-30's scope says so.
PKCE_REFUSALS = {
    "a challenge outside the PKCE alphabet": {"code_challenge": MALFORMED_CODE_CHALLENGE},
    "a challenge method this provider does not offer": {"code_challenge_method": "plain"},
}

# The three scope refusals E0-30 maps to `invalid_scope`, each malformed in a
# different way. The tab is RFC 6749 Appendix A.4's grammar — `scope-token`s are
# separated by one space and by nothing else — and it is the case a bare
# `str.split()` turns into two valid tokens before anything can judge it
# (`docs/MISTAKES.md` entry 29). The second asks for no `openid` at all, which
# OIDC Core §3.1.2.1 requires of every request here. The third names a token this
# provider does not offer.
SCOPE_REFUSALS = {
    "a tab between the tokens": "openid\temail",
    "no openid scope at all": "email profile",
    "a scope token this provider does not offer": "openid wibble",
}

# Where a repeated value sits relative to the real one. **Both orders are the
# test** rather than thoroughness, for the reason the flow module gives: which of
# two values under one name a server reads is the framework's choice and not the
# specification's, so a single-order test reports a pass for whichever half it
# happened to pick and says nothing about the other.
REPEAT_ORDERS = {"the second value first": True, "the second value last": False}

# The two parameters whose duplication has to stay a page, with a second value
# for each that a provider reading the other end would act on. Neither can be
# trusted when it arrives twice, and both are what a redirect target is computed
# from — so there is no address a refusal could safely be delivered to.
CRITICAL_DUPLICATES = {
    "client_id": FORGED_CLIENT_ID,
    "redirect_uri": UNREGISTERED_REDIRECT_URI,
}

# A subject the seed does not carry, and the two shapes a person who belongs on
# the other door would have. **This suite's choice** of spelling; the values say
# what they are. The launch-only pair are near neighbours of the wrong-door
# refusal rather than that refusal itself — see the module docstring — and are
# sent because the outcome must be the same for both.
UNKNOWN_SUBJECT = "e0-30-nobody"
LAUNCH_ONLY_SUBJECTS = {
    "an instructor-only identity": "instructor-only-e0-30",
    "a student-only identity": "student-only-e0-30",
}

# A query parameter a registered redirect URI may legitimately carry: not `code`
# and not `state`, which `ProviderSettings.validate` refuses at registration
# precisely because the authorization response appends them. `tests/unit/
# test_mock_idp_service.py` asserts that such a URI registers; this module
# asserts what an error redirect does to it.
REGISTERED_QUERY_NAME = "tenant"
REGISTERED_QUERY_VALUE = "e0-30"

# The variable that carries the registered redirect URI, transcribed from
# E0-30's own item 3 and from `mock-idp/app/config.py`'s `REDIRECT_URI_VARIABLE`.
# Set on a second provider instance so that one test can drive a registration
# whose query is not empty.
REDIRECT_URI_VARIABLE = "MOCK_IDP_TOOL_REDIRECT_URI"


def parameters_for(
    provider: Any, *, omitting: Sequence[str] = (), **overrides: str
) -> list[tuple[str, str]]:
    """A conformant authorization request as an ordered list of pairs.

    A list rather than the mapping `MockIdentityProvider.authorization_request`
    hands back, because half the cases here are about a name appearing twice and
    a mapping cannot express one (ADR 0062 rule 3, and `begin_from`'s docstring
    in `tests/conftest.py`).
    """
    request, _ = provider.authorization_request(omitting=omitting, **overrides)
    return list(request.items())


def with_repeated(
    parameters: Sequence[tuple[str, str]], name: str, value: str, *, first: bool
) -> list[tuple[str, str]]:
    """`parameters` with `value` added under `name`, beside the value already there.

    `first` puts the added value before the real one and otherwise after it. The
    rest of the request is untouched and stays in order, so the only difference
    between the two calls — and between either of them and a conformant request —
    is the duplicate and where it sits.

    A twin of the one in `test_mock_idp_authorization_code_flow.py`, and a copy
    on purpose: these modules share code only through fixtures (they do not
    import their own `conftest`), and a pure list transform is not the kind of
    hazard `docs/MISTAKES.md` entry 13 is about. What must not be copied is a
    rule that could drift, and this one has no rule in it.
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


def outside_nqschar(value: str) -> list[str]:
    """The characters of `value` that RFC 6749 Appendix A's `NQSCHAR` does not allow.

    `NQSCHAR = %x20-21 / %x23-5B / %x5D-7E` — printable ASCII including the
    space, excluding `"` (%x22) and `\\` (%x5C), and nothing above %x7E. Appendix
    A.8 gives `error_description = 1*NQSCHAR`, so the empty string is out too and
    is asserted separately by the caller.

    Written as a predicate over code points rather than as a regular expression
    or a whitelist string, so that what it refuses is the grammar transcribed
    from the RFC rather than a set of characters somebody thought of.
    """
    return [
        character
        for character in value
        if not (
            0x20 <= ord(character) <= 0x21
            or 0x23 <= ord(character) <= 0x5B
            or 0x5D <= ord(character) <= 0x7E
        )
    ]


def authorize(provider: Any, parameters: Sequence[tuple[str, str]]) -> Any:
    """Send one authorization request exactly as written and answer with what came back.

    No redirect is followed and nothing is asserted: what is under test in this
    module is the response to the authorization request itself, and following it
    would turn the thing being measured into a step on the way to something else.
    """
    path = provider.endpoint_path(
        "authorization_endpoint", "where an authorization request is sent"
    )
    return provider.client.get(path, params=list(parameters))


def refused_by_redirect(provider: Any, response: Any, subject: str) -> dict[str, str]:
    """Require `response` to be §4.1.2.1's error redirect, and hand back its parameters.

    Six assertions rather than one, because "it redirected" is satisfied by
    several things that are not the rule under test:

      - A 2xx is the current behaviour — a 400 page — so the status is checked
        first and by range: RFC 6749 §4.1.2 says the user agent is redirected and
        does not fix which 3xx, so a provider choosing 302 and one choosing 303
        are both conformant and neither is this file's business.
      - The target must be the **registered** URI, compared on scheme, host and
        path. A redirect somewhere else is the open redirector this ticket's
        definition of done names as its one HIGH-shaped mutation.
      - No `code` may ride along. A refusal that also issues an authorization
        code is a session handed out with an error beside it, and a status check
        alone would call that a refusal.
      - No parameter may appear twice in what comes back. This provider refuses a
        duplicated parameter on the way in, and `config.py` refuses to register a
        redirect URI whose query already holds `code` or `state` for exactly this
        reason: a client reading the first `state` of two would compare against a
        value it never generated.
      - `error` must be one of §4.1.2.1's codes rather than a word of this
        provider's own, because a client branches on it.
      - `error_description` must carry something. It is where E0-16's reasoning
        for the refusal survives the change of transport, and this ticket's
        out-of-scope list turns on it: the verdict does not change, only where it
        is delivered.
    """
    registered = provider.registration()["redirect_uri"]
    assert 300 <= response.status_code < 400, (
        f"The provider refused {subject} with status {response.status_code} rather than by "
        f"redirecting to {registered!r}. RFC 6749 §4.1.2.1: once the redirect target has "
        "validated, the error is added to that URI's query and the user agent is sent there. A "
        "page tells the browser's user something and tells the client nothing — it is the branch "
        f"E1's callback cannot reach. Body begins {response.text[:300]!r}."
    )
    location = response.headers.get("location") or ""
    assert location, (
        f"The provider answered {response.status_code} for {subject} with no `Location` header, so "
        "there is nowhere for the browser to go and no error for the client to read."
    )

    sent, back = urlsplit(registered), urlsplit(location)
    assert (back.scheme, back.netloc, back.path) == (sent.scheme, sent.netloc, sent.path), (
        f"The refusal of {subject} was delivered to {location!r}; the registered redirect URI is "
        f"{registered!r}. RFC 6749 §4.1.2.1 permits exactly one destination — the one that was "
        "registered — and any other address is a browser sent somewhere the client never named."
    )

    pairs = parse_qsl(back.query, keep_blank_values=True)
    repeated = sorted({name for name, _ in pairs if [n for n, _ in pairs].count(name) > 1})
    assert not repeated, (
        f"The refusal of {subject} came back carrying {repeated} more than once ({location!r}). "
        "This provider refuses a duplicated parameter on the way in, and a client reading the "
        "first of two values compares against something nobody sent."
    )
    returned = dict(pairs)

    assert "code" not in returned, (
        f"The refusal of {subject} carried an authorization code back to the client "
        f"({location!r}). An error response that also issues a grant has refused nothing: whoever "
        "reads that redirect can redeem it."
    )
    assert returned.get("error") in AUTHORIZATION_ERROR_CODES, (
        f"The refusal of {subject} carried `error`={returned.get('error')!r}, which is not one of "
        f"RFC 6749 §4.1.2.1's codes {sorted(AUTHORIZATION_ERROR_CODES)}. A client branches on "
        "this value, so a word of the provider's own leaves it with nothing to branch on."
    )
    assert returned.get("error_description", "").strip(), (
        f"The refusal of {subject} carried `error_description`="
        f"{returned.get('error_description')!r}. E0-30 turns E0-16's prose into that member and "
        "changes nothing about the verdict — a refusal that arrives with the code and drops the "
        "reason has lost the half a developer acts on."
    )
    return returned


def refused_by_page(provider: Any, response: Any, subject: str) -> None:
    """Require `response` to be a refusal the browser is *not* sent anywhere by.

    The three assertions are the three ways a refusal could leak into a redirect:
    a 3xx status, a `Location` header on any status, and the authorization code
    itself. Asserting the absence of a redirect is weak on its own — the provider
    as it stands redirects nothing at all — so every caller either carries a live
    control or names the test in this module that is one.
    """
    assert not 300 <= response.status_code < 400, (
        f"The provider answered {response.status_code} for {subject} and sent the browser to "
        f"{response.headers.get('location')!r}. RFC 6749 §4.1.2.1: a server that finds the "
        "`client_id` or the `redirect_uri` invalid MUST NOT redirect the user agent — there is no "
        "address it has established the right to send anyone to."
    )
    assert not response.headers.get("location"), (
        f"The provider answered {response.status_code} for {subject} carrying `Location` "
        f"{response.headers.get('location')!r}. A redirect the status does not announce is still a "
        "redirect: several clients and every browser follow a `Location` on a 200."
    )
    assert 400 <= response.status_code < 500, (
        f"The provider answered {response.status_code} for {subject}. A refusal that cannot be "
        "delivered to the client is delivered to the person, as a page saying no — a 2xx would be "
        "the request having been honoured and a 5xx would be the provider having failed to decide."
    )
    _, code, _ = provider.read_authorization_response(response)
    assert code is None, (
        f"The provider refused {subject} with status {response.status_code} and put an "
        f"authorization code ({code!r}) in the response anyway."
    )


# ---------------------------------------------------------------------------
# The control the whole module rests on.
# ---------------------------------------------------------------------------


def test_a_conformant_authorization_request_reaches_the_login_form_rather_than_the_client(
    mock_idp: Any,
) -> None:
    """The live control for every redirect below: this provider does not redirect everything.

    Dies if the split lands the wrong way round — an implementation that builds
    the error redirect before deciding whether there is an error at all. Without
    it, every `error=` assertion in this module is satisfied by a provider that
    sends every request straight back to the registered URI with a constant error
    on it, which is `docs/MISTAKES.md` entry 3 in the shape this ticket makes
    newly available.

    **What it deliberately does not assert is the status.** Whether
    `/oidc/authorize` renders the login form itself or redirects to a page that
    does is the implementer's choice and E0-30 does not touch it, so the question
    asked here is the one that matters: was the browser sent to the *client*
    without anybody being asked who they are. `MockIdentityProvider.begin`
    follows the provider's own redirects and stops at the client's URI, so
    reaching a form through it is the same statement one hop later.
    """
    registered = mock_idp.registration()["redirect_uri"]
    response = authorize(mock_idp, parameters_for(mock_idp))
    location = response.headers.get("location") or ""

    assert not location.startswith(registered), (
        f"A conformant authorization request was answered with {response.status_code} to "
        f"{location!r} — straight back to the client, without anyone being asked who is signing "
        "in. Every refusal test in this module would pass against a provider that does that, so "
        "this is the assertion that says the redirects below are decisions."
    )
    assert mock_idp.begin().form is not None, (
        "A conformant authorization request did not reach a page carrying a login form. E0-30 "
        "changes how a refusal is delivered and nothing about which requests are refused, so a "
        "conformant one still has to reach the form."
    )


# ---------------------------------------------------------------------------
# One test per post-validation refusal, and the code each must carry.
# ---------------------------------------------------------------------------


def test_an_unsupported_response_type_is_refused_as_unsupported_response_type_by_redirect(
    mock_idp: Any,
) -> None:
    """E0-30's first mapping: `response_type` → `unsupported_response_type`.

    Dies if this refusal reverts to a page, and dies if it redirects under
    another code — `invalid_request` here would send a client looking at what it
    failed to send, when what it sent was a flow this provider does not offer.
    `token` rather than a nonsense word on purpose: it is a real response type
    that a real provider may support, so the refusal is about this provider's
    offering rather than about a value nobody could parse.
    """
    parameters = parameters_for(mock_idp, response_type="token")
    state = dict(parameters)["state"]

    returned = refused_by_redirect(
        mock_idp, authorize(mock_idp, parameters), "a request for `response_type=token`"
    )

    assert returned.get("error") == UNSUPPORTED_RESPONSE_TYPE, (
        f"A request for `response_type=token` was refused as {returned.get('error')!r} rather than "
        f"{UNSUPPORTED_RESPONSE_TYPE!r}. RFC 6749 §4.1.2.1 reserves that code for a response type "
        "the server does not support, and the discovery document is where a client reads which "
        "ones it does."
    )
    assert (
        returned.get("state") == state
    ), f"The refusal came back with state {returned.get('state')!r}; the request sent {state!r}."


@pytest.mark.parametrize("case", sorted(SCOPE_REFUSALS))
def test_a_scope_refusal_is_refused_as_invalid_scope_by_redirect(mock_idp: Any, case: str) -> None:
    """E0-30's second mapping: all three scope refusals → `invalid_scope`.

    Dies if any of the three reverts to a page. The sharpest instance of the
    state this ticket replaces is exactly here: the scope refusal's own message
    cites "§4.1.2.1 `invalid_scope`" while being delivered by the one mechanism
    §4.1.2.1 says not to use.

    Three cases in one parametrized test because the mapping is one rule over
    three raise sites; written as three separate tests, a provider that answered
    `invalid_request` for the grammar violation and `invalid_scope` for the other
    two would fail one test and look like one mistake, when what it would be is
    the handler guessing per site — which is what E0-30 removes by putting the
    code on the exception.
    """
    scope = SCOPE_REFUSALS[case]
    parameters = parameters_for(mock_idp, scope=scope)
    state = dict(parameters)["state"]

    returned = refused_by_redirect(mock_idp, authorize(mock_idp, parameters), f"{case} ({scope!r})")

    assert returned.get("error") == INVALID_SCOPE, (
        f"A request carrying {case} ({scope!r}) was refused as {returned.get('error')!r} rather "
        f"than {INVALID_SCOPE!r}. RFC 6749 §4.1.2.1 has one code for a scope that is malformed, "
        "unknown or invalid, and this provider's own message already names it."
    )
    assert (
        returned.get("state") == state
    ), f"The refusal came back with state {returned.get('state')!r}; the request sent {state!r}."


@pytest.mark.parametrize("name", REQUIRED_PARAMETERS)
def test_a_missing_required_parameter_is_refused_as_invalid_request_by_redirect(
    mock_idp: Any, name: str
) -> None:
    """E0-30's third mapping: a missing `state`, `nonce` or `code_challenge` → `invalid_request`.

    Dies if any of the three reverts to a page. The `state` case is the one worth
    reading twice: the parameter that is missing is the parameter the redirect
    would normally echo, so an implementation that reaches for the request's
    `state` while building the redirect raises on it and answers a 500 — which
    this asserts is not what happens, because `refused_by_redirect` requires a
    3xx and a 5xx is not one.

    All three in one parametrized test for the reason the scope cases are: a
    provider that answered a different code for one of them would be a handler
    still deciding per site.
    """
    parameters = parameters_for(mock_idp, omitting=[name])
    assert name not in dict(parameters), (
        f"`parameters_for(omitting=[{name!r}])` still sent `{name}`, so this test would be about a "
        "conformant request. `authorization_request` in tests/conftest.py takes `omitting`."
    )

    returned = refused_by_redirect(mock_idp, authorize(mock_idp, parameters), f"no `{name}`")

    assert returned.get("error") == INVALID_REQUEST, (
        f"A request sent without `{name}` was refused as {returned.get('error')!r} rather than "
        f"{INVALID_REQUEST!r}. RFC 6749 §4.1.2.1 assigns that code to a request 'missing a "
        "required parameter', which is this exactly."
    )


@pytest.mark.parametrize("case", sorted(PKCE_REFUSALS))
def test_a_malformed_pkce_challenge_is_refused_as_invalid_request_by_redirect(
    mock_idp: Any, case: str
) -> None:
    """E0-30's fourth mapping: RFC 7636 §4.4.1's `invalid_request`, with the reason in prose.

    Dies if either reverts to a page, and dies if either is answered
    `invalid_scope` or `unsupported_response_type` by a handler that had one code
    for everything it could not use. Two cases because a challenge the alphabet
    rules out and a method this provider does not offer are different mistakes
    that RFC 7636 gives one code — so `error_description` is the only thing
    telling them apart, and `refused_by_redirect` requires it to say something.

    The malformed challenge is 43 characters long on purpose; a shorter value
    would be turned away for its length before anything looked at its characters,
    and the test would pass without reaching the refusal it is named for.
    """
    parameters = parameters_for(mock_idp, **PKCE_REFUSALS[case])
    state = dict(parameters)["state"]

    returned = refused_by_redirect(mock_idp, authorize(mock_idp, parameters), case)

    assert returned.get("error") == INVALID_REQUEST, (
        f"A request carrying {case} was refused as {returned.get('error')!r} rather than "
        f"{INVALID_REQUEST!r}. RFC 7636 §4.4.1 assigns exactly that code to both, with the reason "
        "in `error_description`."
    )
    assert (
        returned.get("state") == state
    ), f"The refusal came back with state {returned.get('state')!r}; the request sent {state!r}."


# ---------------------------------------------------------------------------
# `state`: echoed exactly when it arrived, and absent when it did not.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("state", [MARKER_STATE, AWKWARD_STATE, PADDED_STATE])
def test_an_error_redirect_echoes_the_state_it_was_sent_byte_for_byte(
    mock_idp: Any, state: str
) -> None:
    """RFC 6749 §4.1.2.1: `state` comes back exactly, and it is the client's CSRF check.

    Dies if `state` is re-encoded rather than echoed, and dies if it is minted,
    trimmed or dropped on the error path — which is where it is easiest to lose,
    because the success path already had a test and the error path had no
    transport at all. E1's callback matches this value against the login it
    started; a value that does not match is a login the client must discard, so a
    provider that mangles `state` on the error path turns every refusal into a
    second, different error at the client.

    The awkward case is the whole point of the pair. A `state` carrying `&`, `=`,
    a space and a percent escape is what separates an echo from a re-encode: the
    marker value survives naive string concatenation and this one does not,
    coming back as two parameters or as a doubly-escaped string. ADR 0062's rule
    for echo semantics, on the direction it did not cover.

    **`PADDED_STATE` was added in E0-30's second fix round** and is the near miss
    for `test_a_refusal_for_a_whitespace_only_state_carries_no_state_parameter_back`
    below. That test says a `state` of nothing but spaces must be treated as
    absent; the wrong way to satisfy it is to strip `state` and work with what is
    left, which rewrites this value — which has real content — into something its
    own client cannot match. Green today and green after the fix: it is here to
    keep the blank rule from being widened into a trimming rule.
    """
    unknown_scope = SCOPE_REFUSALS["a scope token this provider does not offer"]
    parameters = parameters_for(mock_idp, state=state, scope=unknown_scope)

    returned = refused_by_redirect(
        mock_idp, authorize(mock_idp, parameters), f"an unknown scope with state {state!r}"
    )

    assert returned.get("state") == state, (
        f"The refusal came back with state {returned.get('state')!r}; the request sent {state!r}. "
        "RFC 6749 §4.1.2.1 requires the value the client sent, unchanged — a client compares "
        "exactly these two strings, and one that cannot match its own `state` cannot tell its own "
        "refused login from someone else's."
    )


def test_a_refusal_for_a_missing_state_carries_no_state_parameter_back(mock_idp: Any) -> None:
    """RFC 6749 §4.1.2.1's "if present": nothing arrived, so nothing is echoed.

    Dies if the redirect carries `state=` empty, `state=None`, or a value the
    provider invented — all three of which a client reads as a `state` it never
    generated, and the correct client response to that is to discard the
    response. An empty `state` is the likely mutation, because a handler
    formatting its parameters from a mapping with a default of `""` emits the
    name with nothing after it.

    The absence is asserted alongside `refused_by_redirect`'s six, so this is not
    a test that passes on a response that never came: the redirect has to exist,
    reach the registered URI and carry `invalid_request` before the absence is
    read at all.
    """
    parameters = parameters_for(mock_idp, omitting=["state"])

    returned = refused_by_redirect(mock_idp, authorize(mock_idp, parameters), "no `state`")

    assert returned.get("error") == INVALID_REQUEST, (
        f"A request sent without `state` was refused as {returned.get('error')!r} rather than "
        f"{INVALID_REQUEST!r}, so the assertion below would be about the wrong refusal."
    )
    assert "state" not in returned, (
        "The refusal of a request carrying no `state` came back with `state`="
        f"{returned.get('state')!r}. RFC 6749 §4.1.2.1 returns the parameter 'if present in the "
        "client authorization request', and a client that receives one it never sent has been "
        "handed a value it must refuse to match."
    )


@pytest.mark.parametrize("case", sorted(BLANK_STATES))
def test_a_refusal_for_a_whitespace_only_state_carries_no_state_parameter_back(
    mock_idp: Any, case: str
) -> None:
    """A `state` of nothing but spaces is missing on the way in, so it is absent on the way out.

    Kills the mutation the second fix round's third finding measured: the
    provider refuses `state=%20%20%20` **for not having a `state`** and then puts
    `state=%20%20%20` on the redirect it refuses with. One request, two
    incompatible answers to "did a `state` arrive", and the half the client can
    see is the wrong one — it is handed a `state` back, so it looks up a pending
    login by a value the provider has already decided was never sent.

    **Which of the two answers is the right one is not this test's choice, and it
    is not open.** E0-30's out-of-scope list: item 1 "changes the *transport* of a
    refusal, never its verdict — a request refused today is refused after this
    ticket, with the same reasoning in `error_description`." A whitespace-only
    `state` is refused today. So the verdict stays, and the redirect is what has
    to agree with it.

    Two spellings so that "blank" cannot come to mean the one value that was
    measured. A tab is deliberately **not** among them: what this provider counts
    as blank is its own decision, and the rule asserted here is only that
    whatever it refuses the request for lacking, it does not then hand back.

    A separate test rather than a case on
    `test_a_refusal_for_a_missing_state_carries_no_state_parameter_back`, which
    sends no `state` at all. That one is green today and guards the parameter
    being *invented*; this one is red today and guards it being *reflected*.
    Folded together, the new case would be indistinguishable from the old in the
    failure output, and the old test would stop being a green control.
    """
    blank = BLANK_STATES[case]
    parameters = parameters_for(mock_idp, state=blank)
    assert dict(parameters)["state"] == blank, (
        f"`parameters_for(state={blank!r})` sent {dict(parameters).get('state')!r}, so this test "
        "would be about a different value than the one it is named for."
    )

    returned = refused_by_redirect(
        mock_idp, authorize(mock_idp, parameters), f"a `state` of {case}"
    )

    assert returned.get("error") == INVALID_REQUEST, (
        f"A request whose `state` was {blank!r} was refused as {returned.get('error')!r} rather "
        f"than {INVALID_REQUEST!r}. E0-30 leaves the verdict alone and RFC 6749 §4.1.2.1 assigns "
        "that code to a request missing a required parameter, so the assertion below would "
        "otherwise be about a refusal for some other reason."
    )
    assert "state" not in returned, (
        f"A request whose `state` was {blank!r} was refused for want of a `state`, and the refusal "
        f"came back carrying `state`={returned.get('state')!r}. RFC 6749 §4.1.2.1 returns the "
        "parameter 'if present in the client authorization request': the provider has already "
        "judged that none was, and a client handed one anyway is asked to match a value the "
        "provider itself does not believe it received."
    )


# ---------------------------------------------------------------------------
# What the client is handed back: the characters `error_description` may carry.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("case", sorted(POISONED_REQUESTS))
def test_an_error_description_carries_only_characters_rfc_6749_allows_in_one(
    mock_idp: Any, case: str
) -> None:
    """RFC 6749 Appendix A.8: `error_description = 1*NQSCHAR`, whatever the request said.

    Kills the mutation the second fix round's first finding measured: the
    description is built by interpolating the offending value, so whoever sends
    the request chooses the bytes the client receives. A request naming
    `response_type` as `token"\\<script>…§` comes back with the `"`, the `\\` and
    the non-ASCII character in `error_description`, none of which the grammar
    admits — the quote and the backslash end a quoted string early wherever the
    redirect is next read as one, and a value outside ASCII is not something a
    client parsing an OAuth error response has agreed to receive.

    **This asserts nothing at all about the wording**, and that is deliberate.
    The right fix may stop quoting the caller's value entirely, quote a
    normalised form of it, or bound the whole description at the point the
    redirect is built — and the last of those is the one that holds, which is why
    three raise sites are driven rather than the one the reproduction used. A fix
    that sanitises where the reproduction pointed passes one case and fails the
    others.

    What is asserted beside the bound is that the description still **says
    something**: `1*NQSCHAR` is one character or more, and deleting the
    description is the other way to satisfy a character rule. E0-30's own
    out-of-scope list keeps the reasoning for the refusal in that member.
    """
    assert len(POISONED_CODE_CHALLENGE) == 43, (
        f"`POISONED_CODE_CHALLENGE` is {len(POISONED_CODE_CHALLENGE)} characters long. It must be "
        "43 — the shortest a PKCE verifier may be — or the challenge case is refused for its "
        "length before anything looks at what is in it."
    )

    parameters = parameters_for(mock_idp, **POISONED_REQUESTS[case])

    returned = refused_by_redirect(mock_idp, authorize(mock_idp, parameters), case)

    description = returned.get("error_description", "")
    assert description, (
        f"The refusal of {case} came back with `error_description`={description!r}. RFC 6749 "
        "Appendix A.8 is `1*NQSCHAR` — one character or more — and a description deleted to "
        "satisfy a character rule has taken the reason for the refusal with it."
    )

    offending = outside_nqschar(description)
    named = [f"{character!r} (U+{ord(character):04X})" for character in sorted(set(offending))]
    assert not offending, "\n".join(
        [
            f"The refusal of {case} came back with an `error_description` carrying {named}, which "
            "RFC 6749 Appendix A.8's `1*NQSCHAR` does not admit "
            "(`%x20-21 / %x23-5B / %x5D-7E`).",
            "",
            f"The whole value was {description!r}.",
            "",
            "The request chose those characters. A description built by interpolating the "
            "offending parameter lets whoever sends the request decide what bytes arrive at the "
            'client — a `"` or a `\\` ends a quoted string early in whatever reads the redirect '
            "next, and a character outside ASCII is not one an OAuth error response may carry at "
            "all.",
        ]
    )


# ---------------------------------------------------------------------------
# The line: what must never be delivered by redirect, because there is no
# address this provider has established the right to use.
# ---------------------------------------------------------------------------


def test_an_unknown_client_id_is_refused_with_a_page(mock_idp: Any) -> None:
    """The first of the two pre-validation refusals, which E0-30 leaves alone.

    Dies if the split point moves above the `client_id` check. There is no
    registered client at that moment, so there is no registered redirect URI
    either, and the only address available is the one the request supplied —
    which is the open redirector.

    The live control for "this provider does redirect some refusals" is the whole
    top half of this module, and specifically
    `test_an_unregistered_redirect_uri_with_a_second_defect_produces_a_page_and_no_redirect`,
    which asserts both halves in one run. A provider that answered pages for
    everything — today's provider — passes this test and fails every redirect
    test in this module, so this one cannot be silently vacuous while the suite
    is green.
    """
    parameters = parameters_for(mock_idp, client_id=UNKNOWN_CLIENT_ID)

    refused_by_page(
        mock_idp, authorize(mock_idp, parameters), f"an unknown `client_id` ({UNKNOWN_CLIENT_ID!r})"
    )


def test_an_unregistered_redirect_uri_is_refused_with_a_page(mock_idp: Any) -> None:
    """The second, and the one the oldest hole in OAuth is about.

    Dies if a refusal is delivered to an address that failed the registration
    check. RFC 6749 §4.1.2.1: a server that finds the redirect URI invalid "MUST
    NOT automatically redirect the user-agent to the invalid redirect URI".

    The flow module already asserts that no *code* reaches this address; what is
    new here is that no error does either. They are different failures: one hands
    over a session, and the other hands over a service that will send a browser
    anywhere, which is what a phishing chain is built out of.
    """
    parameters = parameters_for(mock_idp, redirect_uri=UNREGISTERED_REDIRECT_URI)

    refused_by_page(
        mock_idp,
        authorize(mock_idp, parameters),
        f"an unregistered `redirect_uri` ({UNREGISTERED_REDIRECT_URI!r})",
    )


def test_an_unregistered_redirect_uri_with_a_second_defect_produces_a_page_and_no_redirect(
    mock_idp: Any,
) -> None:
    """The ordering near miss, and the reason the split point is where it is.

    **This is the mutation the whole module exists to kill**: a refusal computed
    before `redirect_uri` has validated. Every single-defect test here stays
    green against that implementation, because a request that is wrong in exactly
    one place cannot show the ordering: with the registered URI the redirect is
    correct, and with an unregistered URI and nothing else wrong there is no
    error to deliver.

    So this request is wrong on both sides of the line at once: an unregistered
    `redirect_uri` **and** a scope this provider does not offer. An implementation
    that raises the scope refusal before checking the address answers it with a
    redirect carrying `error=invalid_scope` — to the attacker's URI, with the
    victim's browser. E0-30's definition of done calls this its one HIGH-shaped
    mutation.

    **Both halves are asserted in one run**, which is what makes the negative
    half mean something. The same scope defect with the *registered* URI must
    redirect; the same defect with the unregistered one must not. Without the
    first, "it did not redirect" is a true statement about the provider as it
    stands today, which redirects nothing at all — `docs/MISTAKES.md` entry 3.
    """
    unknown_scope = SCOPE_REFUSALS["a scope token this provider does not offer"]

    control = authorize(mock_idp, parameters_for(mock_idp, scope=unknown_scope))
    refused_by_redirect(
        mock_idp, control, f"an unknown scope ({unknown_scope!r}) with the registered redirect URI"
    )

    response = authorize(
        mock_idp,
        parameters_for(mock_idp, scope=unknown_scope, redirect_uri=UNREGISTERED_REDIRECT_URI),
    )

    location = response.headers.get("location") or ""
    assert not location.startswith(UNREGISTERED_REDIRECT_URI), "\n".join(
        [
            f"The provider sent the browser to {location!r}.",
            "",
            f"The request named the unregistered redirect URI {UNREGISTERED_REDIRECT_URI!r} and "
            "also asked for a scope this provider does not offer, and the scope refusal was "
            "computed first. RFC 6749 §4.1.2.1: a server that finds the redirect URI invalid MUST "
            "NOT automatically redirect the user agent to it. This provider is now an open "
            "redirector — anyone who can get a person to open a link can send that person's "
            "browser wherever they like, carrying parameters, from an address the institution "
            "trusts.",
        ]
    )
    refused_by_page(
        mock_idp,
        response,
        "an unregistered `redirect_uri` sent together with an unknown scope",
    )


# ---------------------------------------------------------------------------
# The second place the line is drawn: one name, two values.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("case", sorted(REPEAT_ORDERS))
@pytest.mark.parametrize("name", sorted(CRITICAL_DUPLICATES))
def test_a_duplicated_client_id_or_redirect_uri_is_refused_with_a_page(
    mock_idp: Any, name: str, case: str
) -> None:
    """E0-30's reordering, on the half that stays a page: neither value can be trusted.

    Dies if the duplicate check is moved below the redirect-URI check wholesale —
    which is the tempting simplification, because it makes every duplicate one
    rule. It cannot be: a request carrying two `redirect_uri` values has not
    named an address this provider may send anyone to, and one carrying two
    `client_id` values has not named the client whose registration would decide
    which address that is. Whichever value the framework underneath reads is the
    framework's choice rather than the specification's, so one of the two
    orderings is always the attacker's.

    Both orders and both names, for that reason. A provider that reads the last
    value refuses one ordering and accepts the other, and a single-order test
    reports a pass for whichever half it happened to pick.
    """
    parameters = with_repeated(
        parameters_for(mock_idp), name, CRITICAL_DUPLICATES[name], first=REPEAT_ORDERS[case]
    )

    refused_by_page(
        mock_idp,
        authorize(mock_idp, parameters),
        f"two `{name}` values with {case} ({CRITICAL_DUPLICATES[name]!r})",
    )


@pytest.mark.parametrize("case", sorted(REPEAT_ORDERS))
def test_a_duplicated_scope_is_refused_as_invalid_request_by_redirect(
    mock_idp: Any, case: str
) -> None:
    """E0-30's reordering, on the half that becomes a redirect.

    Dies if the duplicate-parameter check stays where it is — above every
    validation, answering a page for every repeated name. Once `client_id` and
    `redirect_uri` have both validated as single values, the address is known
    good and RFC 6749 §4.1.2.1's transport applies: the request "includes a
    parameter more than once", which §4.1.2.1 calls `invalid_request`.

    **Both values are individually valid** — `openid` and `openid email` — so the
    refusal can only be about the repetition. A duplicate built from one valid
    and one malformed value would be refused either way, and the test would pass
    against a provider that had never noticed the duplication at all.

    This test is the live control for the two page assertions above: it is the
    same request shape, differing only in which name is repeated, so a provider
    that answered a page here as well would fail this and pass those.
    """
    parameters = with_repeated(
        parameters_for(mock_idp), "scope", "openid email", first=REPEAT_ORDERS[case]
    )
    state = dict(parameters)["state"]

    returned = refused_by_redirect(
        mock_idp, authorize(mock_idp, parameters), f"two valid `scope` values with {case}"
    )

    assert returned.get("error") == INVALID_REQUEST, (
        f"A request carrying `scope` twice was refused as {returned.get('error')!r} rather than "
        f"{INVALID_REQUEST!r}. RFC 6749 §4.1.2.1 assigns that code to a request that 'includes a "
        "parameter more than once'; `invalid_scope` would send a client looking at values that "
        "are each perfectly good."
    )
    assert (
        returned.get("state") == state
    ), f"The refusal came back with state {returned.get('state')!r}; the request sent {state!r}."


# ---------------------------------------------------------------------------
# The login form, where the refusal E1 will actually meet comes from.
# ---------------------------------------------------------------------------


def test_a_login_naming_a_subject_this_provider_does_not_know_is_refused_as_access_denied(
    mock_idp: Any,
) -> None:
    """The shape E1's callback has to handle, and the one that will occur in use.

    Dies if this refusal stays a page. **This is the user-cancel shape** E0-30's
    fourth acceptance criterion names: a person who arrives at the login form and
    does not complete it leaves the client holding a pending login with nothing
    to resolve it, and §4.1.2.1's answer is `access_denied` with the `state`
    echoed. The login page offers no explicit cancel control (`mock-idp/app/
    pages.py` builds one select and one submit button), so the refusal is
    produced the way the form can produce one — by naming somebody this provider
    will not sign in — and the response shape is the same one a cancel would
    have.

    Dies also if the code is `invalid_request`: the request was well formed and
    the address was good; what did not happen is a person being signed in.

    The control is
    `test_a_conformant_authorization_request_reaches_the_login_form_rather_than_the_client`
    above, plus the flow module's completed logins and the fresh attempt inside
    `test_a_refused_login_still_spends_the_pending_authorization_request` — this
    provider does sign people in, so the refusal is about who was named.
    """
    attempt = mock_idp.begin(state=MARKER_STATE)
    form = mock_idp.require_login_form(attempt)
    submission = dict(mock_idp.offered_identities(attempt)[0])
    submission[mock_idp.identity_field(form)] = UNKNOWN_SUBJECT

    submitted = mock_idp.submit_login(attempt, submission)

    returned = refused_by_redirect(
        mock_idp, submitted.response, f"a login naming the unknown subject {UNKNOWN_SUBJECT!r}"
    )
    assert returned.get("error") == ACCESS_DENIED, (
        f"A login naming {UNKNOWN_SUBJECT!r} was refused as {returned.get('error')!r} rather than "
        f"{ACCESS_DENIED!r}. RFC 6749 §4.1.2.1: `access_denied` is 'the resource owner or "
        "authorization server denied the request', which is what a person who was not signed in "
        "looks like from the client — and it is the branch E1's callback needs to be able to "
        "reach."
    )
    assert returned.get("state") == MARKER_STATE, (
        f"The refusal came back with state {returned.get('state')!r}; the authorization request "
        f"sent {MARKER_STATE!r}. E1 matches the returned `state` to the pending login before it "
        "consumes it, so a refusal it cannot match is one it must ignore — and the person is then "
        "left on a callback page that can say nothing about what happened."
    )


@pytest.mark.parametrize("case", sorted(LAUNCH_ONLY_SUBJECTS))
def test_a_login_naming_an_identity_that_belongs_on_the_other_door_is_refused_as_access_denied(
    mock_idp: Any, case: str
) -> None:
    """SPEC §2's wrong-door refusal, as near as this seed can be brought to it.

    Dies if this refusal stays a page, and dies if it answers a different code
    from the unknown-subject refusal above — the two are one outcome from a
    client's side, and a provider that distinguished them in the redirect would
    be telling an unauthenticated caller which subjects it knows.

    **What this cannot reach, said rather than implied.** `sign_in` refuses two
    things and this is the second: a seeded person whose assignments do not open
    the web door. No such person exists — every entry in `mock-idp/app/seed.py`
    holds at least one web-door assignment, because E0-16 forbids seeding an
    instructor-only or student-only identity here — so what arrives at the
    provider is an unknown subject wearing the right name. It is a near
    neighbour, kept because SPEC §2's rule is the reason the refusal exists and
    because the outcome must not depend on which of the two fired. The case
    itself is unreachable from outside without changing the seed, which E0-16
    forbids; `docs/MISTAKES.md` entry 3 is why that is written here instead of
    being left to look like coverage.
    """
    attempt = mock_idp.begin(state=MARKER_STATE)
    form = mock_idp.require_login_form(attempt)
    submission = dict(mock_idp.offered_identities(attempt)[0])
    submission[mock_idp.identity_field(form)] = LAUNCH_ONLY_SUBJECTS[case]

    submitted = mock_idp.submit_login(attempt, submission)

    returned = refused_by_redirect(mock_idp, submitted.response, f"a login naming {case}")
    assert returned.get("error") == ACCESS_DENIED, (
        f"A login naming {case} ({LAUNCH_ONLY_SUBJECTS[case]!r}) was refused as "
        f"{returned.get('error')!r} rather than {ACCESS_DENIED!r}. SPEC §2 gives the instructor "
        "and the student the launch door only, and from the client's side that refusal is the "
        "same event as any other person who did not sign in."
    )
    assert returned.get("state") == MARKER_STATE, (
        f"The refusal came back with state {returned.get('state')!r}; the authorization request "
        f"sent {MARKER_STATE!r}."
    )


def test_a_refused_login_still_spends_the_pending_authorization_request(mock_idp: Any) -> None:
    """The rule E0-30 says it does not change, asserted so that it cannot change quietly.

    A refused login spends the pending request. Dies if the refusal path returns
    early — building the error redirect and leaving the pending request in place
    — which is the natural shape of the change this ticket asks for and which
    turns one authorization request into an unlimited number of login attempts.
    Nothing else in the suite would notice: the refusal would look correct, and
    the second attempt would succeed and produce a perfectly valid session.

    The control is a fresh attempt in the same test, signing in as the same
    person, which must produce a code. Without it, "the replay produced no code"
    is satisfied by a login form that never works.
    """
    attempt = mock_idp.begin()
    form = mock_idp.require_login_form(attempt)
    identity = mock_idp.offered_identities(attempt)[0]

    refused_submission = dict(identity)
    refused_submission[mock_idp.identity_field(form)] = UNKNOWN_SUBJECT
    refused = mock_idp.submit_login(attempt, refused_submission)
    assert refused.refused, (
        f"A login naming {UNKNOWN_SUBJECT!r} obtained an authorization code ({refused.code!r}), so "
        "there is no refusal here for the replay below to follow."
    )

    replayed = mock_idp.submit_login(attempt, identity)

    control = mock_idp.begin()
    control_submitted = mock_idp.submit_login(control, mock_idp.offered_identities(control)[0])
    assert control_submitted.code, (
        "A seeded identity signing in on a fresh authorization request produced no code (status "
        f"{control_submitted.response.status_code}), so the refusal above would be a fact about a "
        "login form that never works rather than about the pending request having been spent."
    )

    assert replayed.refused, (
        "After a refused login, the same pending authorization request was used again and issued "
        f"an authorization code ({replayed.code!r}, sent to {replayed.location!r}). A refused "
        "login spends the request: one authorization request is one attempt, and a pending "
        "request that survives its own refusal is an unlimited number of them against a `state` "
        "and a challenge the client generated once."
    )


# ---------------------------------------------------------------------------
# A registered redirect URI that already carries a query.
# ---------------------------------------------------------------------------


def test_error_parameters_are_added_to_a_registered_query_rather_than_replacing_it(
    mock_idp: Any, mock_idps: Any
) -> None:
    """E0-30: the error is *added to* the registered URI's query, so `&` where one exists.

    Dies if the refusal is built by appending `?error=...` to the registered URI,
    which produces a second `?` and a query no client can parse; dies if it is
    built by replacing the query, which drops whatever the deployment registered.
    Neither failure is visible against the shipped registration, whose URI
    carries no query at all — which is why this test starts a second provider
    with one.

    A query on a redirect URI is ordinary: a tenant, a locale, a return path.
    `ProviderSettings.validate` refuses only a query already carrying `code` or
    `state`, and `tests/unit/test_mock_idp_service.py` asserts that an unrelated
    one registers. What that unit test cannot see is what the authorization
    endpoint then does with it.
    """
    shipped = mock_idp.registration()["redirect_uri"]
    assert "?" not in shipped, (
        f"The shipped redirect URI is {shipped!r} and already carries a query, so appending one "
        "below would produce a URI with two. Send the registered value through as it stands."
    )

    registered = f"{shipped}?{REGISTERED_QUERY_NAME}={REGISTERED_QUERY_VALUE}"
    provider = mock_idps({REDIRECT_URI_VARIABLE: registered})
    assert provider.registration()["redirect_uri"] == registered, (
        f"The second provider published redirect URI {provider.registration()['redirect_uri']!r} "
        f"rather than the {registered!r} it was configured with, so this test would be driving the "
        f"default registration. `{REDIRECT_URI_VARIABLE}` is the variable E0-30 item 3 names."
    )

    unknown_scope = SCOPE_REFUSALS["a scope token this provider does not offer"]
    parameters = parameters_for(provider, scope=unknown_scope)
    state = dict(parameters)["state"]

    returned = refused_by_redirect(
        provider, authorize(provider, parameters), "an unknown scope on a registration with a query"
    )

    assert returned.get(REGISTERED_QUERY_NAME) == REGISTERED_QUERY_VALUE, (
        f"The refusal was delivered to a URI carrying {sorted(returned)}, and the registered "
        f"`{REGISTERED_QUERY_NAME}={REGISTERED_QUERY_VALUE}` is not among them. E0-30: the error "
        "parameters are added to the registered URI's query rather than substituted for it — a "
        "deployment that registered a return path or a tenant gets it back."
    )
    assert returned.get("error") == INVALID_SCOPE and returned.get("state") == state, (
        f"The refusal carried `error`={returned.get('error')!r} and `state`="
        f"{returned.get('state')!r}; it should carry {INVALID_SCOPE!r} and {state!r}. A "
        "registration that already had a query must not change which refusal arrives."
    )
