"""The mock platform's HTTP surface: six endpoints, and one issuer key per process.

Run it with `uvicorn app.main:create_app --factory`, the same way the backend is
run. There is no module-level application object, and here that is load-bearing
rather than stylistic: **the issuer key is generated when the application is
built**, so one application is one key, and starting a second platform really is
a second platform. SPEC §9.1 asks for issuer keys generated per test run rather
than fixtures checked into the repository, and a module-level singleton would
quietly turn "per run" into "per import".

The routes are closures over the settings, the seed and the key for the same
reason. Nothing reaches a key through a global, so there is no arrangement of
imports that lets two applications share one.

**Configuration is read here, at build time**, not in a lifespan handler and not
per request. The test fixture in `tests/conftest.py` sets the environment around
the import and the factory call and restores it before lifespan runs, so a
platform that read its issuer in `startup` would read whatever the process
happened to hold — and would pass every test that does not set configuration.

**No launch payload is logged.** SPEC §10 forbids personally identifiable
information in logs, and while this platform holds none (see `app.seed`), a
request logger that dumped `id_token` payloads would be a pattern for E1 to copy
into a service that does hold it. So nothing here logs: the `id_token` is
returned to the caller and written nowhere.

Stated precisely, because "nothing is logged" would be a claim this file cannot
make. Uvicorn's own access log is on, and it records the method, the path and the
status of every request. It never sees an `id_token` — that is returned in a
response body — but an authorization request sent by `GET` rather than by `POST`
carries `state`, `nonce` and `login_hint` in its query string, and the access log
records those. All three are values this platform invented or was handed by a
test; none is a person. Measured against the running container rather than
assumed.
"""

from typing import Any
from urllib.parse import parse_qsl

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse

from app.config import (
    AUTHORIZATION_PATH,
    DISCOVERY_PATH,
    HEALTH_PATH,
    JWKS_PATH,
    LAUNCH_PAGE_PATH,
    REGISTRATION_PATH,
    PlatformSettings,
)
from app.launch import (
    AuthorizationRequestError,
    id_token_claims,
    resolve_launch,
)
from app.pages import authorization_response_page, launch_page, registration_values
from app.seed import seeded_platform
from app.signing import SIGNATURE_ALGORITHM, IssuerKey

SERVICE_NAME = "mock-lms"

SUMMARY = "A development-only LTI 1.3 platform to launch Pulse from (SPEC §9.2)."

# How an OIDC authorization request arrives when a tool posts it.
FORM_MEDIA_TYPE = "application/x-www-form-urlencoded"


def create_app() -> FastAPI:
    """Build the platform: read the environment, seed it, and generate its key."""
    settings = PlatformSettings.from_environment()
    platform = seeded_platform()
    key = IssuerKey.generate()

    app = FastAPI(
        title="Pulse Surveys — mock LMS",
        summary=SUMMARY,
        # No OpenAPI schema, and so no `/docs` and no `/redoc`. This service's
        # contract is OIDC and LTI 1.3, and its discovery document describes it
        # to the only audience that matters. Leaving them on would also put a
        # second route carrying the word `auth` in the routing table
        # (`/docs/oauth2-redirect`), which is one more thing for a tool — or a
        # test discovering endpoints by name — to have to disambiguate.
        openapi_url=None,
    )
    app.state.settings = settings

    @app.get(HEALTH_PATH, summary="Liveness, for the Compose health check")
    def healthz() -> dict[str, str]:
        """Answer from nothing but this process. No downstream, no key material."""
        return {"service": SERVICE_NAME, "status": "ok"}

    @app.get(LAUNCH_PAGE_PATH, response_class=HTMLResponse, summary="The launch page")
    def launch() -> HTMLResponse:
        """A form a browser can click through, per E0-14's scope."""
        return HTMLResponse(launch_page(settings, platform))

    @app.get(DISCOVERY_PATH, summary="OIDC discovery")
    def discovery() -> dict[str, Any]:
        """What a tool reads to find the endpoints, rather than guessing paths.

        Only what this platform actually serves is advertised. There is no
        `token_endpoint` here because there is no token endpoint: LTI Advantage's
        service calls are E0-15's, and an advertised endpoint that answers
        nothing is a record asserting something untrue.
        """
        return {
            "issuer": settings.issuer,
            "authorization_endpoint": settings.authorization_url,
            "jwks_uri": settings.jwks_url,
            "response_types_supported": ["id_token"],
            "response_modes_supported": ["form_post"],
            "subject_types_supported": ["public"],
            "id_token_signing_alg_values_supported": [SIGNATURE_ALGORITHM],
            "scopes_supported": ["openid"],
            "claims_supported": ["iss", "sub", "aud", "exp", "iat", "nonce"],
        }

    @app.get(JWKS_PATH, summary="The platform's public key set")
    def jwks() -> dict[str, Any]:
        """The public half of this process's issuer key, and nothing else.

        Built from `public_jwk()`, which assembles the public members rather than
        filtering the private ones out of a serialised pair — the difference
        being that a member nobody thought to filter cannot appear.
        """
        return {"keys": [key.public_jwk()]}

    @app.get(REGISTRATION_PATH, summary="Everything needed to register this platform")
    def registration() -> dict[str, str]:
        """The registration a developer pastes into `lti_platform`, in one fetch.

        E0-14's scope: "seeded platform registration values matching what
        `lti_platform` from E0-08 expects, so a developer can register the mock in
        one step". The keys are the column names, which is what makes "one step"
        literal rather than an exercise in translation.
        """
        return registration_values(settings)

    @app.api_route(
        AUTHORIZATION_PATH,
        methods=["GET", "POST"],
        response_class=HTMLResponse,
        summary="The authorization endpoint: answers with a signed id_token",
    )
    async def authorize(request: Request) -> HTMLResponse:
        """Answer a tool's authorization request with a signed launch.

        Both methods, because OIDC lets the tool choose and a platform that
        accepted only one would make that choice for it.

        The body is parsed with `parse_qsl` rather than through FastAPI's
        `Form(...)` or Starlette's `request.form()`, and that is a locked-closure
        constraint rather than a preference: both of those require
        `python-multipart`, which this project does not lock, and Starlette 1.6
        asserts on it even for `application/x-www-form-urlencoded`. An
        authorization request is a flat mapping of strings, so `parse_qsl` is the
        whole of what is needed.

        `state` comes back exactly as it arrived. That is the platform's whole
        obligation to it: the value is the tool's, and a platform that
        re-encoded it breaks the tool's cross-site request forgery check in a way
        that reads as a bug in the tool.
        """
        if request.method == "POST":
            media_type = request.headers.get("content-type", "").split(";")[0].strip().lower()
            if media_type != FORM_MEDIA_TYPE:
                raise HTTPException(
                    status_code=415,
                    detail=(
                        f"The authorization request was posted as {media_type!r}. An OIDC "
                        f"authorization request is {FORM_MEDIA_TYPE!r}."
                    ),
                )
            body = (await request.body()).decode("utf-8", errors="replace")
            parameters = dict(parse_qsl(body, keep_blank_values=True))
        else:
            parameters = dict(request.query_params)

        try:
            resolved = resolve_launch(parameters, settings, platform)
        except AuthorizationRequestError as refusal:
            # 400 rather than a redirect carrying an OIDC error code. The request
            # that failed is often the one naming where to redirect *to*, and
            # answering a bad `redirect_uri` by using it is how an open
            # redirector is built.
            raise HTTPException(status_code=400, detail=str(refusal)) from refusal

        id_token = key.compact_jws(id_token_claims(resolved, settings))
        return HTMLResponse(
            authorization_response_page(
                id_token=id_token,
                state=resolved.state,
                redirect_uri=resolved.redirect_uri,
            )
        )

    return app
