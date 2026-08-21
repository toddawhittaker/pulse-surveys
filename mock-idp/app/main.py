"""The mock provider's HTTP surface, and one signing key per process.

Run it with `uvicorn app.main:create_app --factory`, the same way the backend and
the mock platform are run. There is no module-level application object, and here
that is load-bearing rather than stylistic: **the signing key is generated when
the application is built**, so one application is one key, and starting a second
provider really is a second provider. SPEC §9.1 asks for issuer keys generated
per test run rather than fixtures checked into the repository, and a module-level
singleton would quietly turn "per run" into "per import".

The routes are closures over the settings, the seed, the key and the flow store
for the same reason. Nothing reaches a key or a pending login through a global,
so there is no arrangement of imports that lets two applications share one.

**Configuration is read here, at build time**, not in a lifespan handler and not
per request — the reason `mock-lms/app/main.py` gives, and the reason the test
fixture can start this application under an environment it sets around the
import.

**Nothing is logged.** SPEC §10 forbids personally identifiable information in
logs, and a request logger that dumped `id_token` payloads would be a pattern for
E1 to copy into a service whose sessions are real people. Stated precisely,
because "nothing is logged" is a claim this file cannot make on its own: uvicorn's
access log is on, and it records the method, the path and the status of every
request. An authorization request arrives by `GET`, so its query string — the
`state`, the `nonce` and the PKCE challenge — reaches that log. All three are
values a client invented for one login and none is a person. The `sub` of whoever
signs in does **not** reach it: the login is a `POST` with the identity in its
body, and the session comes back in a token response body. That is deliberate,
and it is the shape E1 should copy — the mock platform's per-user AGS result route
is the counter-example it should not.
"""

from typing import Any
from urllib.parse import parse_qsl

from fastapi import FastAPI, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from app.config import (
    AUTHORIZATION_PATH,
    DISCOVERY_PATH,
    HEALTH_PATH,
    INDEX_PATH,
    JWKS_PATH,
    LOGIN_PATH,
    MOCK_REGISTRATION_PATH,
    TOKEN_PATH,
    ProviderSettings,
)
from app.flow import (
    AuthorizationRedirectError,
    AuthorizationRequestError,
    Flows,
    TokenRequestError,
    authorization_response,
    discovery_document,
    error_response,
    repeated_parameters,
)
from app.pages import index_page, login_page, refusal_page, registration_document
from app.seed import seeded_directory
from app.signing import IssuerKey

SERVICE_NAME = "mock-idp"

SUMMARY = "A development-only OpenID Connect provider for the web-login roles (SPEC §9.2)."

# How a form submission and a token request both arrive.
FORM_MEDIA_TYPE = "application/x-www-form-urlencoded"

# What a refusal answers with when there is nowhere to deliver it: a 400 and a
# page. That is the case where the request named no address this provider has
# established the right to send anyone to — an unknown `client_id`, an
# unregistered `redirect_uri`, either of the two arriving twice, or a login
# answering no pending request. RFC 6749 §4.1.2.1 forbids the redirect there and
# requires it everywhere else, and `app.flow.Flows.begin` is where the two sides
# are separated.
REFUSED = 400

# Sending a browser onward: after a successful login, and to the registered
# redirect URI with a refusal on it. 303 rather than 302, so the browser follows
# with `GET` whatever it arrived with — the login was a `POST`, and a 302 leaves
# the method to the client. RFC 6749 §4.1.2 fixes no particular 3xx.
SEE_OTHER = 303

# RFC 6749 §5.1: a token response is never cached, successful or not. A client
# library that cached one would replay somebody else's session out of a proxy.
NO_STORE = {"cache-control": "no-store", "pragma": "no-cache"}


async def form_body(request: Request, subject: str) -> dict[str, str]:
    """Decode an `application/x-www-form-urlencoded` body into a flat mapping.

    Parsed with `parse_qsl` rather than through FastAPI's `Form(...)` or
    Starlette's `request.form()`, and that is a locked-closure constraint rather
    than a preference: both of those require `python-multipart`, which this
    project does not lock, and Starlette asserts on it even for a plain form
    body. A login and a token request are both flat mappings of strings, so
    `parse_qsl` is the whole of what is needed.

    `keep_blank_values` is on, so a parameter sent empty arrives as an empty
    string rather than vanishing — "sent blank" and "not sent" are different
    mistakes, and the refusals in `app.flow` can only tell them apart if the
    parser does.

    A repeated parameter is refused here rather than in the mapping, because a
    mapping is where the repetition disappears: `dict()` keeps the last pair and
    nothing after it can tell there were two (RFC 6749 §3.1).

    **The duplicate check spans the whole request and the values do not.** RFC
    6749 §3.1 is a statement about the request, not about one encoding of it, so
    the query string is counted here even though nothing reads a value out of it:
    a `POST` carrying `code` in the body and `code` in the query is one parameter
    sent twice, and this provider refused it in neither place until it was
    measured doing so. Values still come from the body alone — §4.1.3 puts a
    token request there — because honouring a query parameter as well would be a
    second place a parameter can arrive, which is the shape being closed rather
    than a fix for it. A server that merges the two, as Spring Authorization
    Server and anything behind a query-folding gateway does, sees the duplicate
    this one now sees.
    """
    media_type = request.headers.get("content-type", "").split(";")[0].strip().lower()
    if media_type != FORM_MEDIA_TYPE:
        raise ValueError(
            f"The {subject} arrived as {media_type!r}. It is {FORM_MEDIA_TYPE!r} (RFC 6749 §4.1)."
        )
    body = (await request.body()).decode("utf-8", errors="replace")
    pairs = parse_qsl(body, keep_blank_values=True)
    repeated = repeated_parameters([*request.query_params.multi_items(), *pairs])
    if repeated:
        raise ValueError(
            f"The {subject} carries {repeated} more than once, counting its query string and "
            "its body together. RFC 6749 §3.1: a request parameter MUST NOT be included more "
            "than once."
        )
    return dict(pairs)


def create_app() -> FastAPI:
    """Build the provider: read the environment, seed it, and generate its key."""
    settings = ProviderSettings.from_environment()
    directory = seeded_directory()
    key = IssuerKey.generate()
    flows = Flows()

    app = FastAPI(
        title="Pulse Surveys — mock IdP",
        summary=SUMMARY,
        # No OpenAPI schema, and so no `/docs` and no `/redoc`. This service's
        # contract is OpenID Connect, and its discovery document describes it to
        # the only audience that matters. Leaving them on would also put
        # `/docs/oauth2-redirect` in the routing table, which is a second route
        # carrying an OAuth word for a client — or a test discovering endpoints
        # by name — to have to disambiguate.
        openapi_url=None,
    )
    app.state.settings = settings

    @app.get(HEALTH_PATH, summary="Liveness, for the Compose health check")
    def healthz() -> dict[str, str]:
        """Answer from nothing but this process. No downstream, no key material."""
        return {"service": SERVICE_NAME, "status": "ok"}

    @app.get(INDEX_PATH, response_class=HTMLResponse, summary="What this is and who it knows")
    def index() -> HTMLResponse:
        """A page for a person: the registration, and the seeded identities."""
        return HTMLResponse(index_page(settings, directory))

    @app.get(DISCOVERY_PATH, summary="OpenID Connect discovery")
    def discovery() -> dict[str, Any]:
        """What a client reads to configure itself, rather than guessing paths.

        Built by `app.flow`, beside the code that enforces what it advertises, so
        that "S256 is required" and "S256 is advertised" cannot become two
        different answers.
        """
        return discovery_document(settings)

    @app.get(JWKS_PATH, summary="The provider's public key set")
    def jwks() -> dict[str, Any]:
        """The public half of this process's signing key, and nothing else.

        Built from `public_jwk()`, which assembles the public members rather than
        filtering the private ones out of a serialised pair — the difference
        being that a member nobody thought to filter cannot appear.
        """
        return {"keys": [key.public_jwk()]}

    @app.get(MOCK_REGISTRATION_PATH, summary="Mock only: the registered client and the seed")
    def registration() -> JSONResponse:
        """Everything a client or a later ticket needs, in one fetch (ADR 0058)."""
        return JSONResponse(registration_document(settings, directory))

    @app.get(
        AUTHORIZATION_PATH,
        summary="The authorization endpoint: checks the request, then asks who you are",
    )
    def authorize(request: Request) -> Response:
        """Check an authorization request and answer with the login form.

        `GET` only. OIDC Core 1.0 §3.1.2.1 requires `GET` and permits `POST`, and
        a browser navigating to a login page uses the first; serving one shape is
        one shape to get right.

        **A refusal comes back one of two ways, and which one is not this
        route's decision.** `app.flow.Flows.begin` refuses with an address
        attached once it has established one, and without an address until then,
        so the two exception types are the split point rather than anything
        counted here. The pairs are handed over as pairs because the duplicate
        rule is one of the checks that straddles it, and a mapping is where a
        repeated name stops being visible (RFC 6749 §3.1).
        """
        try:
            pending = flows.begin(list(request.query_params.multi_items()), settings)
        except AuthorizationRedirectError as refusal:
            return RedirectResponse(error_response(refusal), status_code=SEE_OTHER)
        except AuthorizationRequestError as refusal:
            return HTMLResponse(refusal_page(str(refusal)), status_code=REFUSED)
        return HTMLResponse(login_page(settings, pending, directory))

    @app.post(LOGIN_PATH, summary="The login form's submission: issues an authorization code")
    async def login(request: Request) -> Response:
        """Sign in as the chosen identity and send the browser back with a code.

        The response is a redirect to the **registered** redirect URI — the one
        checked when the authorization request arrived, carried here on the
        server side rather than in this form, so that nothing about where a code
        is delivered depends on what was just posted. A refusal goes to the same
        address, carrying `access_denied` instead of a code (RFC 6749 §4.1.2.1),
        and for the same reason: the address is the one the pending request
        holds, never one this submission named.

        A login that answers no pending request is the exception, and it is a
        page: there is no checked address behind it to send anyone to.
        """
        try:
            submitted = await form_body(request, "login")
        except ValueError as refusal:
            return HTMLResponse(refusal_page(str(refusal)), status_code=REFUSED)
        try:
            pending, issued = flows.sign_in(submitted, directory)
        except AuthorizationRedirectError as refusal:
            return RedirectResponse(error_response(refusal), status_code=SEE_OTHER)
        except AuthorizationRequestError as refusal:
            return HTMLResponse(refusal_page(str(refusal)), status_code=REFUSED)
        return RedirectResponse(authorization_response(pending, issued), status_code=SEE_OTHER)

    @app.post(TOKEN_PATH, summary="The token endpoint: exchanges a code for a session")
    async def token(request: Request) -> JSONResponse:
        """Exchange one authorization code for one session, or refuse in JSON.

        Every refusal carries RFC 6749 §5.2's `error` member, because that is
        what tells a client the difference between a rejected grant and a
        provider that fell over — and a `Cache-Control: no-store`, because §5.1
        requires it of a response carrying a token and a client library that
        cached one would replay somebody's session.
        """
        try:
            submitted = await form_body(request, "token request")
        except ValueError as refusal:
            return JSONResponse(
                {"error": "invalid_request", "error_description": str(refusal)},
                status_code=REFUSED,
                headers=NO_STORE,
            )
        try:
            issued = flows.redeem(submitted, settings, directory, key)
        except TokenRequestError as refusal:
            return JSONResponse(refusal.body, status_code=refusal.status_code, headers=NO_STORE)
        return JSONResponse(issued, headers=NO_STORE)

    return app
