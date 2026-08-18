"""The authorization code flow with PKCE: what is checked, stored, and issued.

This is the provider half of SPEC §2's second entry door. The tool half —
starting the flow, remembering `state` and `nonce`, validating the `id_token`
against the published keys, and turning a session into a purview — is E1's, and
E0-16's out-of-scope list says so.

**Nothing here is lenient, and that is the ticket's own instruction.** E0-16's
definition of done: "An identity provider that is lenient in the wrong place
teaches the tool-side code bad habits." So every parameter OIDC Core 1.0 §3.1.2.1
and RFC 7636 make part of this flow is required and checked, and each refusal
says which one failed:

- **`client_id` and `redirect_uri` are checked first, and a failure of either is
  answered with a page rather than a redirect.** RFC 6749 §4.1.2.1: a server that
  finds the redirect URI invalid "MUST NOT automatically redirect the user-agent
  to the invalid redirect URI". Redirecting an error to an address that just
  failed validation is how an open redirector is built, and here it would be one
  with an authorization code attached.
- **PKCE is required, S256 only.** A provider that checks a verifier when one
  arrives and issues a session when none does offers no protection at all: an
  attacker holding a stolen code omits the parameter. RFC 7636 §4.6 requires the
  refusal, and `plain` is refused as well as absent — it is permitted by the
  specification and it protects nothing on a network anyone can read.
- **`state` and `nonce` are required**, although RFC 6749 only recommends the
  first and OIDC only requires the second for the implicit flow. They are the
  client's cross-site-request-forgery and replay defences; a provider that lets a
  client skip either teaches E1 to skip it, and E1's client is the one that
  matters.
- **A code is single-use, and a *failed* exchange spends it too.** RFC 6749
  §4.1.2 makes the code single-use; burning it on the first attempt, whatever the
  attempt's outcome, is the stricter reading and means a stolen code cannot be
  brute-forced against the verifier check.
- **Nothing is a client secret.** This provider registers one public client and
  advertises `token_endpoint_auth_method: none`, so PKCE is what proves
  possession, and `invalid_client` is an error this module never returns. That is
  not cosmetic: a token endpoint that refused for an unsent credential would
  refuse the replayed code and the mismatched verifier for a reason that has
  nothing to do with either.

**All state is per application and in memory**, which is the arrangement
`docs/adr/0049-the-mock-gradebook-is-per-application-state-in-memory.md` records
for the platform's gradebook and holds here for the same reasons: restarting the
container forgets every pending login and every unspent code, and two providers
started in one test process share nothing.
"""

import base64
import hashlib
import re
import secrets
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, urlsplit, urlunsplit

from app.config import ProviderSettings
from app.seed import MockPerson, SeededDirectory
from app.signing import SIGNATURE_ALGORITHM, IssuerKey

# The response type and grant this provider serves. RFC 6749's authorization code
# flow, which is what E0-16's third criterion names, and the only one here.
RESPONSE_TYPE = "code"
GRANT_TYPE = "authorization_code"

# The scope OIDC Core 1.0 §3.1.2.1 makes an OpenID Connect request an OpenID
# Connect request. A request without it is a plain OAuth 2.0 one, and this
# provider has nothing to offer it.
OPENID_SCOPE = "openid"

# The two other scopes a client may ask for, and **what each one buys**: OIDC
# Core 1.0 §5.4 binds `preferred_username` to `profile` and `email` plus
# `email_verified` to `email`, so asking for neither means a session carrying
# neither. Azure AD, Okta and Google all behave that way, and a mock that handed
# the claims over regardless would teach E1 that `email` always arrives — which
# it does, right up until Pulse is pointed at a real provider.
PROFILE_SCOPE = "profile"
EMAIL_SCOPE = "email"
SUPPORTED_SCOPES = (OPENID_SCOPE, PROFILE_SCOPE, EMAIL_SCOPE)

# Which claims each scope grants. The roles claim is deliberately not in here: it
# is bound to `openid` because it is the whole reason this provider exists to be
# asked, and a client that had to know to ask for it would be a client that finds
# out it did not at resolution time.
CLAIMS_BY_SCOPE = {
    PROFILE_SCOPE: ("preferred_username",),
    EMAIL_SCOPE: ("email", "email_verified"),
}

# The PKCE transformation this provider accepts. RFC 7636 §4.2 requires S256 of
# any server supporting PKCE; `plain` is permitted by the specification and is
# refused here, because it sends the verifier itself in the authorization
# request and so protects nothing against anyone who can read one.
CODE_CHALLENGE_METHOD = "S256"

# RFC 7636's shape for **both** PKCE parameters: `43*128unreserved`, which §4.1's
# ABNF gives the verifier and §4.3's gives the challenge. One rule and one pair of
# bounds, because it is one production in the specification and two copies could
# disagree about a parameter whose whole job is to be compared with the other.
PKCE_MINIMUM_LENGTH = 43
PKCE_MAXIMUM_LENGTH = 128
PKCE_ALPHABET = re.compile(r"[A-Za-z0-9\-._~]+")

# How long a login page is good for, and how long an unspent authorization code
# is. RFC 6749 §4.1.2 recommends a maximum code lifetime of ten minutes; one
# minute is stricter and is far longer than the round trip it covers, which is a
# browser posting a form and a client redeeming a code it has just been handed.
PENDING_REQUEST_LIFETIME_SECONDS = 300
AUTHORIZATION_CODE_LIFETIME_SECONDS = 60

# How long an issued session is good for. Five minutes, the same figure the
# platform's launch token carries, and for the same reason: it is long enough for
# a client to validate what it has just been given and short enough that a
# session lifted out of a log is worth nothing by the time anyone reads it.
ID_TOKEN_LIFETIME_SECONDS = 300

# The token type OIDC Core 1.0 §3.1.3.3 fixes for this flow. Spelled as RFC 6749
# §7.1 registers it; the value is case-insensitive and this is the registered
# casing.
BEARER = "Bearer"

# How many bytes of entropy go into a code and into an access token. 32 bytes is
# 256 bits, which is well past anything guessable, and `secrets` is what draws it.
OPAQUE_VALUE_BYTES = 32

# Where this provider states what a person may do. A namespaced claim, because
# RFC 7519 §4 reserves the unprefixed name space for registered claims and `roles`
# is not one of them — a client that met an unprefixed `roles` from two providers
# would have two different things under one name. The namespace is Pulse's own,
# at a domain RFC 2606 reserves.
ROLES_CLAIM = "https://pulse.example/claims/roles"

# The claims a session carries, advertised in the discovery document so a client
# can see the shape before it asks for one.
SUPPORTED_CLAIMS = (
    "iss",
    "sub",
    "aud",
    "exp",
    "iat",
    "auth_time",
    "nonce",
    "email",
    "email_verified",
    "preferred_username",
    ROLES_CLAIM,
)


class AuthorizationRequestError(ValueError):
    """An authorization request cannot be answered, and why.

    Carries a prose reason rather than an OAuth error code, because it is
    rendered on a page for whoever is debugging a login at eleven at night and
    the reason is what they need. The route turns it into a 400.
    """


@dataclass(frozen=True)
class TokenRequestError(Exception):
    """A token request is refused, as the code and description RFC 6749 §5.2 defines.

    A code *and* a description, because the two have different readers: a client
    branches on `error`, and a person reads `error_description`. RFC 6749 makes
    the first required, which is what tells a client the difference between a
    rejected grant and a provider that fell over.
    """

    error: str
    description: str
    status_code: int = 400

    @property
    def body(self) -> dict[str, str]:
        """The refusal as the JSON object a client parses."""
        return {"error": self.error, "error_description": self.description}


@dataclass(frozen=True)
class PendingAuthorization:
    """One checked authorization request, waiting for somebody to sign in.

    Held server-side and named in the login form by an opaque identifier, rather
    than round-tripped through hidden fields. The difference is the whole point:
    with the request in hidden fields, everything checked at the authorization
    endpoint would have to be checked again on the way back — and anything the
    second check missed would be a parameter the browser got to choose *after*
    the first check passed. The `redirect_uri` is the one that matters.
    """

    request_id: str
    client_id: str
    redirect_uri: str
    state: str
    nonce: str
    scope: str
    code_challenge: str
    expires_at: float


@dataclass(frozen=True)
class AuthorizationCode:
    """One issued code, and everything the exchange has to check it against."""

    code: str
    client_id: str
    redirect_uri: str
    nonce: str
    subject: str
    scope: str
    code_challenge: str
    expires_at: float


def now() -> float:
    """The current instant, in one place, so a test reading this file knows where."""
    return time.time()


def base64url(raw: bytes) -> str:
    """Encode `raw` as base64url with the padding RFC 7636 and JOSE both omit."""
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def challenge_for(verifier: str) -> str:
    """The S256 challenge RFC 7636 §4.2 derives from `verifier`.

    The base64url of the SHA-256 of the **ASCII** verifier, unpadded. Written
    here once and used only to compare, so the provider recomputes exactly what
    the client computed rather than storing anything the client sent twice.
    """
    return base64url(hashlib.sha256(verifier.encode("ascii")).digest())


def pkce_shape_problem(value: str) -> str | None:
    """Why `value` is not a well-formed PKCE parameter, or `None` if it is.

    Checked at both ends — the challenge when it is registered, the verifier when
    it is compared — because **neither check is only about conformance**. The
    challenge is compared with `secrets.compare_digest`, which refuses two strings
    it cannot treat as ASCII, and the verifier is hashed as ASCII because RFC 7636
    §4.2 computes the digest over those octets. So a character outside this set
    raises inside the comparison instead of being refused by it, and the provider
    answers "we fell over" where the honest answer is "your grant is invalid".
    Both were reproduced before this function existed.

    A reason rather than an exception, because the two callers refuse in different
    vocabularies: an authorization request is answered with a page, and a token
    request with RFC 6749 §5.2's `error` object.
    """
    if not PKCE_MINIMUM_LENGTH <= len(value) <= PKCE_MAXIMUM_LENGTH:
        return (
            f"it is {len(value)} characters, and RFC 7636 makes it between "
            f"{PKCE_MINIMUM_LENGTH} and {PKCE_MAXIMUM_LENGTH}"
        )
    if not PKCE_ALPHABET.fullmatch(value):
        return (
            "it carries characters outside the unreserved set RFC 7636 allows — "
            "`A-Z`, `a-z`, `0-9`, `-`, `.`, `_` and `~`"
        )
    return None


def repeated_parameters(pairs: Sequence[tuple[str, str]]) -> list[str]:
    """The parameter names `pairs` carries more than once, sorted.

    RFC 6749 §3.1: request parameters "MUST NOT be included more than once".
    Both of this service's entry points build a mapping out of pairs — a query
    string at the authorization endpoint, a form body at the login and token
    endpoints — and a mapping is exactly where a duplicate stops being visible:
    `dict()` keeps the last one and nothing downstream can tell that there were
    two. So the question is asked of the pairs, once, before anything sees the
    mapping.

    A list rather than an exception, for the same reason `pkce_shape_problem`
    returns a reason: an authorization request is refused with a page and a token
    request with RFC 6749 §5.2's `error` object, and the rule should not have to
    know which it is talking to.

    Not exploitable on this provider as it stands — a code is bound to the
    redirect URI the server stored, so `?client_id=evil&client_id=<real>` cannot
    send a session anywhere new — and it is leniency in the direction E0-16's
    definition of done names: a tool built against a provider that shrugs at a
    duplicated parameter learns a habit its next platform will not tolerate.
    """
    seen: dict[str, int] = {}
    for name, _ in pairs:
        seen[name] = seen.get(name, 0) + 1
    return sorted(name for name, count in seen.items() if count > 1)


def submitted(parameters: Mapping[str, Any], name: str) -> str:
    """One parameter exactly as it arrived, or the empty string if it did not.

    **Nothing here trims anything, and that is the whole point of the function.**
    A provider that strips a value before looking at it has decided what the
    client meant instead of checking what it sent, and three of this service's
    obligations are broken by exactly that: RFC 7636 §4.1 gives the PKCE
    parameters an ABNF that whitespace violates, so trimming makes the shape
    check structurally unable to refuse the shapes it exists to refuse; RFC 6749
    §4.1.2 requires `state` back as "the exact value received from the client";
    and OIDC Core §3.1.3.7 step 11 has the client compare the `nonce` it sent
    with the one in the token. A stripped value passes through all three looking
    correct and comes back as something the client did not send.

    **What the trimming actually cost is worse than a shape check that could not
    fire, and it is worth stating exactly.** For a stored challenge over some
    verifier `v`, the provider accepted every string that trimmed to `v` — so the
    value PKCE binds was widened from one string to an unbounded set of them, and
    a `code_verifier` that is not the string the challenge was computed over was
    a successful redemption. Measured both ways round on a running instance: a
    challenge registered over `"a" * 43` and redeemed with `" " + "a" * 43 + "\n"`
    answered **200 with an `id_token`** before this function existed and
    `invalid_grant` after. Keycloak, Okta and Auth0 all refuse it, and
    `base64.encodebytes()` appends exactly that newline — so a client minting its
    verifier that way passes here and fails at the first real provider, with an
    error naming the verifier rather than the encoder.
    """
    value = parameters.get(name)
    return "" if value is None else str(value)


def required(parameters: Mapping[str, Any], name: str, subject: str) -> str:
    """One parameter that must be present, returned unaltered, or a refusal naming it.

    Presence is judged on the *trimmed* value and the *untrimmed* one is handed
    back. That split is deliberate: a parameter sent as three spaces carries
    nothing a client could have meant, so saying "it carries no `state`" is more
    use than "your `state` is malformed" — but every check downstream of this
    has to see what actually arrived, so nothing is repaired on the way past.
    """
    value = submitted(parameters, name)
    if not value.strip():
        raise AuthorizationRequestError(
            f"The {subject} carries no `{name}`. It carries {sorted(parameters)}."
        )
    return value


class Flows:
    """Every login this provider has started or finished, for one application.

    Two stores, both single-use: a pending authorization is spent by the login
    that answers it, and a code is spent by the first exchange that names it. Both
    expire, and expired entries are pruned on each write rather than by a
    background task — there is no clock in this service beyond the requests it
    answers, and a mock with a scheduler in it is a mock with a lifecycle to
    debug.
    """

    def __init__(self) -> None:
        self._pending: dict[str, PendingAuthorization] = {}
        self._codes: dict[str, AuthorizationCode] = {}

    # -- the authorization endpoint -----------------------------------------

    def begin(
        self, parameters: Mapping[str, Any], settings: ProviderSettings
    ) -> PendingAuthorization:
        """Check an authorization request and remember it until somebody signs in.

        The order of the checks is load-bearing, not stylistic. `client_id` and
        `redirect_uri` come first because every later refusal is answered with a
        page rather than a redirect, and answering *any* refusal by redirecting
        to an address this method has not yet validated is the hole RFC 6749
        §4.1.2.1 is about.
        """
        subject = "authorization request"

        client_id = required(parameters, "client_id", subject)
        if client_id != settings.client_id:
            raise AuthorizationRequestError(
                f"No registration for `client_id` {client_id!r}. This provider has one "
                f"registered client, {settings.client_id!r}; `GET /mock/registration` publishes "
                "it."
            )

        redirect_uri = required(parameters, "redirect_uri", subject)
        if redirect_uri != settings.redirect_uri:
            raise AuthorizationRequestError(
                f"`redirect_uri` {redirect_uri!r} is not registered for this client. The "
                f"registered one is {settings.redirect_uri!r}, compared exactly as RFC 6749 "
                "§3.1.2.3 requires. A provider that sent a code to an address it was handed is "
                "an open redirector with a session attached, so this refusal is a page rather "
                "than a redirect (RFC 6749 §4.1.2.1)."
            )

        response_type = required(parameters, "response_type", subject)
        if response_type != RESPONSE_TYPE:
            raise AuthorizationRequestError(
                f"The authorization request asks for `response_type` {response_type!r}. This "
                f"provider serves the authorization code flow, {RESPONSE_TYPE!r}, and nothing "
                "else — an implicit or hybrid response would put a session in a URL."
            )

        scope = required(parameters, "scope", subject)
        asked = scope.split()
        if OPENID_SCOPE not in asked:
            raise AuthorizationRequestError(
                f"The authorization request asks for scope {scope!r}, which does not include "
                f"{OPENID_SCOPE!r}. Without it this is a plain OAuth 2.0 request and there is no "
                "`id_token` to issue (OIDC Core 1.0 §3.1.2.1)."
            )
        # RFC 6749 §3.3 lets a server either refuse an unknown scope or ignore it
        # and say so in the response. **Refusing is the honest half here**, and it
        # is what Okta and Azure AD do: this provider serves exactly three scopes
        # and issues no refresh token, so granting `offline_access` — or anything
        # else a client hopefully asked for — would be a promise it cannot keep.
        # The set is in the discovery document as `scopes_supported`, so a client
        # can see it before it sends anything.
        unknown = sorted(set(asked) - set(SUPPORTED_SCOPES))
        if unknown:
            raise AuthorizationRequestError(
                f"The authorization request asks for {unknown}, which this provider does not "
                f"serve. It serves {list(SUPPORTED_SCOPES)}, and its discovery document says so "
                "in `scopes_supported` (RFC 6749 §3.3, §4.1.2.1 `invalid_scope`)."
            )
        # Deduplicated, in the order asked, so what comes back in the token
        # response is a grant a client can compare with its own request.
        granted = " ".join(dict.fromkeys(asked))

        state = required(parameters, "state", subject)
        nonce = required(parameters, "nonce", subject)

        code_challenge = required(parameters, "code_challenge", subject)
        malformed = pkce_shape_problem(code_challenge)
        if malformed is not None:
            raise AuthorizationRequestError(
                f"`code_challenge` is malformed: {malformed}. Registering it as it stands would "
                "produce a code no exchange could ever redeem."
            )

        method = submitted(parameters, "code_challenge_method")
        if method != CODE_CHALLENGE_METHOD:
            raise AuthorizationRequestError(
                f"The authorization request offers `code_challenge_method` {method!r}. This "
                f"provider requires {CODE_CHALLENGE_METHOD!r} (RFC 7636 §4.2): `plain` sends the "
                "verifier itself in this request, and an absent method defaults to it."
            )

        pending = PendingAuthorization(
            request_id=secrets.token_urlsafe(OPAQUE_VALUE_BYTES),
            client_id=client_id,
            redirect_uri=redirect_uri,
            state=state,
            nonce=nonce,
            scope=granted,
            code_challenge=code_challenge,
            expires_at=now() + PENDING_REQUEST_LIFETIME_SECONDS,
        )
        self._prune()
        self._pending[pending.request_id] = pending
        return pending

    # -- the login form's submission ----------------------------------------

    def sign_in(
        self,
        parameters: Mapping[str, Any],
        directory: SeededDirectory,
    ) -> tuple[PendingAuthorization, AuthorizationCode]:
        """Answer one login: resolve the person, spend the request, issue a code.

        The request is spent whatever the outcome, so a submitted form cannot be
        replayed — including the refusals, which is the case worth saying out
        loud: a login that is refused is still a login that happened.

        **The refusal below is SPEC §2's door rule and not a lookup failure.**
        `may_use_web_login` is computed from the person's assignments, and the
        same property decides which people the form offers, so there is one rule
        rather than two that could disagree. A person who holds only an
        instructor or a student assignment is refused here for the reason the
        ticket gives: web login is not their door. A subject nobody seeded is
        refused too, and from outside the two look identical — E0-16 forbids
        seeding either launch-only role, so this provider has no way to tell a
        launch-only person it has never heard of from anybody else it has never
        heard of, and both answers are the same one.
        """
        pending = self._spend_pending(submitted(parameters, "request"))

        subject = required(parameters, "sub", "login")
        person = directory.person(subject)
        if person is None:
            raise AuthorizationRequestError(
                f"No seeded identity {subject!r}. This provider signs in the people it was "
                "seeded with and nobody else; `GET /mock/registration` lists them. SPEC §2 keeps "
                "web login for the leadership, Care and Admin roles — an instructor or a student "
                "enters by LTI launch, which is the mock LMS's door and not this one."
            )
        if not person.may_use_web_login:
            raise AuthorizationRequestError(
                f"{subject!r} holds {[role.value for role in person.launch_only_roles]} and "
                "nothing that opens this door. SPEC §2: entry doors are a property of the "
                "assignment, and instructor and student assignments enter by LTI launch only."
            )

        issued = AuthorizationCode(
            code=secrets.token_urlsafe(OPAQUE_VALUE_BYTES),
            client_id=pending.client_id,
            redirect_uri=pending.redirect_uri,
            nonce=pending.nonce,
            subject=person.subject,
            scope=pending.scope,
            code_challenge=pending.code_challenge,
            expires_at=now() + AUTHORIZATION_CODE_LIFETIME_SECONDS,
        )
        self._prune()
        self._codes[issued.code] = issued
        return pending, issued

    # -- the token endpoint -------------------------------------------------

    def redeem(
        self,
        parameters: Mapping[str, Any],
        settings: ProviderSettings,
        directory: SeededDirectory,
        key: IssuerKey,
    ) -> dict[str, Any]:
        """Exchange a code for a session, or refuse with an RFC 6749 §5.2 error.

        Every refusal below is `invalid_grant` or `invalid_request`, and none is
        `invalid_client`: the registered client is public and authenticates with
        PKCE alone, so a client credential is never missing because it is never
        expected. That matters beyond conformance — two of E0-16's criteria are
        refusals from this endpoint, and a provider that refused for an unsent
        secret would satisfy both while asserting nothing about either.
        """
        grant_type = submitted(parameters, "grant_type")
        if grant_type != GRANT_TYPE:
            raise TokenRequestError(
                error="unsupported_grant_type",
                description=(
                    f"`grant_type` {grant_type!r} is not served here. This provider serves "
                    f"{GRANT_TYPE!r}, which is the flow its discovery document advertises."
                ),
            )

        code = submitted(parameters, "code")
        if not code.strip():
            raise TokenRequestError(
                error="invalid_request",
                description="The token request carries no `code` (RFC 6749 §4.1.3).",
            )

        # Spent on the way in, before anything else is checked, so that a code
        # cannot be replayed against the verifier check either. RFC 6749 §4.1.2
        # makes a code single-use; this is that rule with no exception for an
        # exchange that then fails.
        issued = self._codes.pop(code, None)
        if issued is None or issued.expires_at <= now():
            raise TokenRequestError(
                error="invalid_grant",
                description=(
                    "That authorization code is unknown, expired, or has already been redeemed. "
                    "A code is good once and for "
                    f"{AUTHORIZATION_CODE_LIFETIME_SECONDS}s (RFC 6749 §4.1.2)."
                ),
            )

        client_id = submitted(parameters, "client_id")
        if client_id != issued.client_id or client_id != settings.client_id:
            raise TokenRequestError(
                error="invalid_grant",
                description=(
                    f"`client_id` {client_id!r} did not issue that code. A code belongs to the "
                    "client that asked for it (RFC 6749 §4.1.3)."
                ),
            )

        redirect_uri = submitted(parameters, "redirect_uri")
        if redirect_uri != issued.redirect_uri:
            raise TokenRequestError(
                error="invalid_grant",
                description=(
                    f"`redirect_uri` {redirect_uri!r} is not the one the authorization request "
                    "named. RFC 6749 §4.1.3 requires it back, identically, so that a code "
                    "obtained through one redirect cannot be spent under another."
                ),
            )

        self._require_pkce(parameters, issued)

        person = directory.person(issued.subject)
        if person is None:
            # Unreachable while the seed is a constant: the code carries a
            # subject this service resolved before issuing it. It is here because
            # "the person went away between the login and the exchange" is a real
            # state for a provider with a mutable directory, and a `None` reaching
            # the claims builder would be a session for nobody.
            raise TokenRequestError(
                error="invalid_grant",
                description=(
                    f"The identity {issued.subject!r} that code was issued for is no longer "
                    "seeded."
                ),
            )

        return self._session(person, issued, settings, key)

    def _require_pkce(self, parameters: Mapping[str, Any], issued: AuthorizationCode) -> None:
        """RFC 7636 §4.6: the verifier must be present, well formed, and match.

        Three refusals rather than one, because they are three different mistakes
        and a client reading `error_description` should be told which it made. All
        three are `invalid_grant`, which is what §4.6 specifies. What "well formed"
        means, and why it is checked rather than caught, is on `pkce_shape_problem`
        above — the challenge is checked against the same rule when it arrives.

        The comparison is `compare_digest`, not `==`. Both values are public in
        the sense that neither is a long-lived secret, and the timing of a
        base64 comparison is not a realistic attack on a provider that only ever
        signs invented people — but a mock is where habits are formed, and a
        string comparison against a credential is the habit E0-16's definition of
        done exists to stop E1 inheriting.
        """
        verifier = submitted(parameters, "code_verifier")
        if not verifier.strip():
            raise TokenRequestError(
                error="invalid_grant",
                description=(
                    "The token request carries no `code_verifier`, and the authorization request "
                    "registered a challenge. RFC 7636 §4.6 requires this exchange to be refused: "
                    "a provider that issued a session here would offer no protection at all, "
                    "since anyone holding a stolen code would simply omit the parameter."
                ),
            )
        malformed = pkce_shape_problem(verifier)
        if malformed is not None:
            raise TokenRequestError(
                error="invalid_grant",
                description=f"`code_verifier` is malformed: {malformed}.",
            )
        if not secrets.compare_digest(challenge_for(verifier), issued.code_challenge):
            raise TokenRequestError(
                error="invalid_grant",
                description=(
                    "`code_verifier` does not match the `code_challenge` the authorization "
                    "request registered (RFC 7636 §4.6). That code has been spent; start a new "
                    "authorization request."
                ),
            )

    # -- what a session is --------------------------------------------------

    def _session(
        self,
        person: MockPerson,
        issued: AuthorizationCode,
        settings: ProviderSettings,
        key: IssuerKey,
    ) -> dict[str, Any]:
        """The token response: an access token, and the `id_token` that is the session.

        The access token is opaque and **grants nothing**. There is no userinfo
        endpoint and no resource server here, so it exists because RFC 6749 §5.1
        makes it a required member of a successful response and because a client
        library will refuse a response without one. Saying so is worth a line: a
        mock that issued a bearer token which actually opened something would be
        a mock with an authorization model, which is E1's and E9's work.
        """
        issued_at = int(now())
        granted = issued.scope.split()
        available = {
            "preferred_username": person.subject,
            "email": person.email,
            "email_verified": True,
        }
        claims: dict[str, Any] = {
            "iss": settings.issuer,
            "sub": person.subject,
            "aud": settings.client_id,
            "iat": issued_at,
            "auth_time": issued_at,
            "exp": issued_at + ID_TOKEN_LIFETIME_SECONDS,
            "nonce": issued.nonce,
            ROLES_CLAIM: [role.value for role in person.web_login_roles],
        }
        # Only the claims the granted scopes cover. A response that declared
        # `openid` and carried `email` would contradict itself, and a client
        # reading `id_token["email"]` here would be reading a claim no real
        # provider sends on an `openid`-only grant (OIDC Core 1.0 §5.4).
        for scope in granted:
            for claim in CLAIMS_BY_SCOPE.get(scope, ()):
                claims[claim] = available[claim]

        return {
            "access_token": secrets.token_urlsafe(OPAQUE_VALUE_BYTES),
            "token_type": BEARER,
            "expires_in": ID_TOKEN_LIFETIME_SECONDS,
            # The grant, not the request and not a constant. RFC 6749 §5.1 makes
            # this member required whenever the two differ, and this provider
            # refuses the scopes it does not serve rather than narrowing them
            # silently — so what a client reads here is what it asked for, and
            # the claims above are exactly what it covers.
            "scope": issued.scope,
            "id_token": key.compact_jws(claims),
        }

    # -- housekeeping -------------------------------------------------------

    def _spend_pending(self, request_id: str) -> PendingAuthorization:
        """Take the pending request this login answers, and forget it."""
        if not request_id:
            raise AuthorizationRequestError(
                "The login carries no `request`, so there is no authorization request for it to "
                "answer. Start at the authorization endpoint."
            )
        pending = self._pending.pop(request_id, None)
        if pending is None or pending.expires_at <= now():
            raise AuthorizationRequestError(
                "That login page has expired or has already been used. A login page is good once "
                f"and for {PENDING_REQUEST_LIFETIME_SECONDS}s; start a new authorization request."
            )
        return pending

    def _prune(self) -> None:
        """Drop everything that has expired, so neither store grows without bound."""
        instant = now()
        for request_id in [
            key for key, pending in self._pending.items() if pending.expires_at <= instant
        ]:
            self._pending.pop(request_id, None)
        for code in [key for key, issued in self._codes.items() if issued.expires_at <= instant]:
            self._codes.pop(code, None)


def discovery_document(settings: ProviderSettings) -> dict[str, Any]:
    """The provider metadata a client configures itself from (OIDC Discovery 1.0 §3).

    **Only what this provider actually serves is advertised.** There is no
    `userinfo_endpoint`, no `registration_endpoint` and no `end_session_endpoint`,
    because none of them exists here: an advertised endpoint that answers nothing
    fails at the point of use, in a client, with a 404 that reads as the client's
    bug. The same rule the mock platform's document follows (ADR 0036).

    `code_challenge_methods_supported` is RFC 8414's member and is how a client
    learns, before it sends anything, that PKCE is available — and this provider
    requires it, so a client that could not discover it would guess wrong in the
    one direction that costs.
    """
    return {
        "issuer": settings.issuer,
        "authorization_endpoint": settings.authorization_url,
        "token_endpoint": settings.token_url,
        "jwks_uri": settings.jwks_url,
        "response_types_supported": [RESPONSE_TYPE],
        "response_modes_supported": ["query"],
        "grant_types_supported": [GRANT_TYPE],
        "subject_types_supported": ["public"],
        "id_token_signing_alg_values_supported": [SIGNATURE_ALGORITHM],
        "scopes_supported": list(SUPPORTED_SCOPES),
        "claims_supported": list(SUPPORTED_CLAIMS),
        "code_challenge_methods_supported": [CODE_CHALLENGE_METHOD],
        # The registered client is public: it holds no secret and proves
        # possession with PKCE. Advertised so a client library configures itself
        # for that rather than looking for a credential nobody issued.
        "token_endpoint_auth_methods_supported": ["none"],
    }


def authorization_response(pending: PendingAuthorization, issued: AuthorizationCode) -> str:
    """Where the browser goes next: the registered redirect, carrying code and state.

    `state` comes back exactly as it arrived. That is this provider's whole
    obligation to it — the value is the client's, and a provider that re-encoded
    it would break the client's cross-site-request-forgery check in a way that
    reads as a bug in the client.

    The query is built by hand rather than with `urlencode` over a dict so that
    the order is fixed and readable in a log; both values are drawn from
    `secrets.token_urlsafe` or echoed from a request that has already been
    checked, and `quote` is applied to each so that an unusual `state` cannot
    add a parameter of its own.
    """
    split = urlsplit(pending.redirect_uri)
    added = f"code={quote(issued.code, safe='')}&state={quote(pending.state, safe='')}"
    query = f"{split.query}&{added}" if split.query else added
    return urlunsplit((split.scheme, split.netloc, split.path, query, split.fragment))
