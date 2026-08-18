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
from collections.abc import Mapping
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

# The two other scopes a client may ask for, and what they add: the claims a
# session already carries. They are accepted rather than required, because a
# conformant client asks for what it needs and this provider's whole population
# is eight invented people.
SUPPORTED_SCOPES = (OPENID_SCOPE, "profile", "email")

# The PKCE transformation this provider accepts. RFC 7636 §4.2 requires S256 of
# any server supporting PKCE; `plain` is permitted by the specification and is
# refused here, because it sends the verifier itself in the authorization
# request and so protects nothing against anyone who can read one.
CODE_CHALLENGE_METHOD = "S256"

# RFC 7636 §4.1's bounds on a verifier, checked before it is compared. A verifier
# outside them is not a near miss, it is a client that has not read the
# specification, and saying so is more use than "the code did not match".
VERIFIER_MINIMUM_LENGTH = 43
VERIFIER_MAXIMUM_LENGTH = 128

# And §4.1's alphabet: the unreserved characters of RFC 3986. Checked for the
# same reason as the lengths, plus one of its own — the challenge is computed
# over the verifier's **ASCII** octets, so a character outside this set has no
# ASCII encoding and would raise inside the comparison rather than be refused by
# it.
VERIFIER_ALPHABET = re.compile(r"[A-Za-z0-9\-._~]+")

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


def required(parameters: Mapping[str, Any], name: str, subject: str) -> str:
    """One parameter that must be present and non-empty, or a refusal naming it."""
    value = str(parameters.get(name) or "").strip()
    if not value:
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
        if OPENID_SCOPE not in scope.split():
            raise AuthorizationRequestError(
                f"The authorization request asks for scope {scope!r}, which does not include "
                f"{OPENID_SCOPE!r}. Without it this is a plain OAuth 2.0 request and there is no "
                "`id_token` to issue (OIDC Core 1.0 §3.1.2.1)."
            )

        state = required(parameters, "state", subject)
        nonce = required(parameters, "nonce", subject)

        code_challenge = required(parameters, "code_challenge", subject)
        method = str(parameters.get("code_challenge_method") or "").strip()
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
            scope=scope,
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
        pending = self._spend_pending(str(parameters.get("request") or "").strip())

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
        grant_type = str(parameters.get("grant_type") or "").strip()
        if grant_type != GRANT_TYPE:
            raise TokenRequestError(
                error="unsupported_grant_type",
                description=(
                    f"`grant_type` {grant_type!r} is not served here. This provider serves "
                    f"{GRANT_TYPE!r}, which is the flow its discovery document advertises."
                ),
            )

        code = str(parameters.get("code") or "").strip()
        if not code:
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

        client_id = str(parameters.get("client_id") or "").strip()
        if client_id != issued.client_id or client_id != settings.client_id:
            raise TokenRequestError(
                error="invalid_grant",
                description=(
                    f"`client_id` {client_id!r} did not issue that code. A code belongs to the "
                    "client that asked for it (RFC 6749 §4.1.3)."
                ),
            )

        redirect_uri = str(parameters.get("redirect_uri") or "").strip()
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

        Four refusals rather than one, because they are four different mistakes
        and a client reading `error_description` should be told which it made. All
        four are `invalid_grant`, which is what §4.6 specifies.

        The alphabet check is not tidiness. `challenge_for` encodes the verifier
        as **ASCII**, because §4.2 says the challenge is computed over the ASCII
        octets, so a verifier carrying a character outside that raises inside the
        comparison — and a provider that answered a malformed parameter with a
        500 would be answering "we fell over" where the honest answer is "your
        grant is invalid". Checked before the digest, not caught after it.

        The comparison is `compare_digest`, not `==`. Both values are public in
        the sense that neither is a long-lived secret, and the timing of a
        base64 comparison is not a realistic attack on a provider that only ever
        signs invented people — but a mock is where habits are formed, and a
        string comparison against a credential is the habit E0-16's definition of
        done exists to stop E1 inheriting.
        """
        verifier = str(parameters.get("code_verifier") or "").strip()
        if not verifier:
            raise TokenRequestError(
                error="invalid_grant",
                description=(
                    "The token request carries no `code_verifier`, and the authorization request "
                    "registered a challenge. RFC 7636 §4.6 requires this exchange to be refused: "
                    "a provider that issued a session here would offer no protection at all, "
                    "since anyone holding a stolen code would simply omit the parameter."
                ),
            )
        if not VERIFIER_MINIMUM_LENGTH <= len(verifier) <= VERIFIER_MAXIMUM_LENGTH:
            raise TokenRequestError(
                error="invalid_grant",
                description=(
                    f"`code_verifier` is {len(verifier)} characters. RFC 7636 §4.1 makes it "
                    f"between {VERIFIER_MINIMUM_LENGTH} and {VERIFIER_MAXIMUM_LENGTH}."
                ),
            )
        if not VERIFIER_ALPHABET.fullmatch(verifier):
            raise TokenRequestError(
                error="invalid_grant",
                description=(
                    "`code_verifier` carries characters outside the unreserved set RFC 7636 §4.1 "
                    "allows — `A-Z`, `a-z`, `0-9`, `-`, `.`, `_` and `~`."
                ),
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
        claims: dict[str, Any] = {
            "iss": settings.issuer,
            "sub": person.subject,
            "aud": settings.client_id,
            "iat": issued_at,
            "auth_time": issued_at,
            "exp": issued_at + ID_TOKEN_LIFETIME_SECONDS,
            "nonce": issued.nonce,
            "email": person.email,
            "email_verified": True,
            "preferred_username": person.subject,
            ROLES_CLAIM: [role.value for role in person.web_login_roles],
        }
        return {
            "access_token": secrets.token_urlsafe(OPAQUE_VALUE_BYTES),
            "token_type": BEARER,
            "expires_in": ID_TOKEN_LIFETIME_SECONDS,
            "scope": OPENID_SCOPE,
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
