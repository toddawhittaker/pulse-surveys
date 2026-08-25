"""Beginning an LTI 1.3 launch, and deciding whether the one that came back holds.

SPEC §7.3 and E0-18. The platform half of this protocol is `mock-lms/app/launch.py`,
built by E0-14, which said in as many words that validating what it produces was
somebody else's work. This module is that somebody, for the depth E0 needs.

**What E1 owns and this deliberately does not do**, from E0-18's boundary
section: replay windows, clock-skew tolerance, cookieless iframes, platform-side
state storage, provisioning, any `user` row for a launching subject, any session
that outlives the launch, and any purview computation. What is here is the set
E0-18's acceptance criteria name — signature, `aud`, `iss`, `deployment_id`,
`exp`, `state`, `nonce` — because "absence of *basic* state/nonce/signature
checks is not tolerable even briefly".

**The order of the two legs, since they are easy to confuse.** The platform's
launch page posts an OIDC third-party-initiated login request to `/lti/login`
carrying `iss`, `login_hint`, `target_link_uri` and `lti_message_hint`; neither
`state` nor `nonce` exists yet, and both are *this tool's* to mint. The tool then
sends the browser to the platform's authorization endpoint, and the platform
answers by posting a signed `id_token` back to `/lti/launch` with the tool's own
`state` beside it.

**Nothing here is lenient**, for the reason E0-14 gives about its own half: this
is the first tool code a real token reaches, and it is the first thing E1 reads.
Every refusal is a `LaunchRefusedError` naming what failed, and the router turns it
into a 4xx page rather than a redirect — answering a request that failed
validation by redirecting to an address it supplied is how an open redirector is
built.
"""

import secrets
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import httpx
import jwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings
from app.models.lti import LtiDeployment, LtiPlatform
from app.services.tokens import TokenVerificationError, same_opaque_value, verified_claims

__all__ = [
    "LAUNCH_PATH",
    "LOGIN_PATH",
    "Initiation",
    "LaunchRefusedError",
    "begin_a_launch",
    "verified_launch",
]

# Where this tool answers. Written here rather than in the router because
# `redirect_uri` is built from `LAUNCH_PATH` and the router declares the same
# path, and two copies of a URL a platform compares *exactly* is the shape
# `docs/MISTAKES.md` entry 13 is about. Both mocks default to these paths
# (`mock-lms/app/config.py`), which is what makes the stack work unconfigured.
LOGIN_PATH = "/lti/login"
LAUNCH_PATH = "/lti/launch"

# The LTI 1.3 message claims this module reads, spelled as the specification
# spells them. A claim under any other name is a claim no conformant library
# reads.
LTI_CLAIM_PREFIX = "https://purl.imsglobal.org/spec/lti/claim/"
DEPLOYMENT_ID_CLAIM = f"{LTI_CLAIM_PREFIX}deployment_id"

# What the OIDC implicit flow the LTI 1.3 security framework specifies requires
# a tool to ask for. Constants rather than settings: LTI fixes all three, and a
# knob for any of them could only ever be turned to a value no platform serves.
AUTHORIZATION_REQUEST_CONSTANTS = {
    "scope": "openid",
    "response_type": "id_token",
    "response_mode": "form_post",
    "prompt": "none",
}

# Bytes behind a `state` and a `nonce`. 24 urlsafe bytes is 32 characters of
# base64 and is far past anything guessable; the values are opaque to the
# platform, which hands both back untouched.
#
# Named for what it sizes rather than for the property it has, because
# `app.api.auth` has a constant of its own for the same *kind* of value at a
# different size: 32, which is RFC 7636's minimum PKCE verifier length and is
# load-bearing there. One name holding two numbers in two modules reads as
# shared and is not.
STATE_NONCE_BYTES = 24


class LaunchRefusedError(Exception):
    """A launch cannot be admitted, and why in words a person can act on.

    Carries no claim value and no part of any token — a refusal reaches an HTML
    page and possibly a log, and a launch token is a credential (SPEC §10).
    """


@dataclass(frozen=True)
class Initiation:
    """The authorization request a login initiation produces, and what to remember.

    `parameters` rather than a finished URL: the router assembles the redirect
    out of these and `authorization_endpoint` (`app.api.deps.with_query`).

    **`authorization_endpoint` is read off the registration that resolved this
    launch**, and it is the whole of E1-05's first criterion. It was a
    process-wide setting while `lti_platform` had no column for it (ADR 0075),
    which is right for one registered platform and wrong for two: a launch from
    platform B resolved B's registration and then sent the browser to A's
    address, carrying B's client ID and this tool's `state` and `nonce`. Carried
    on the initiation rather than looked up again in the router, so the row that
    decided the client ID is unarguably the row that decides the address.
    """

    parameters: dict[str, str]
    state: str
    nonce: str
    authorization_endpoint: str


def registered_platform(session: Session, issuer: str) -> LtiPlatform:
    """The one `lti_platform` row for `issuer`, or a refusal.

    **The lookup is by issuer alone, and the request's own `client_id` is
    ignored.** Every value a platform needs is present in the initiation request
    it sends, so a login endpoint that assembled its redirect out of those values
    would work perfectly against the one platform anybody tests with and would
    redirect a browser to whoever asked — an open redirect with the launch
    protocol's name on it. Reading the client ID out of the row is what makes the
    registration, rather than the caller, decide which tool this is.

    **More than one row for one issuer is refused rather than guessed.** LTI 1.3
    allows it — one LMS registering this tool twice, a pilot beside production,
    which is why `lti_platform` is unique on `(issuer, client_id)` and not on the
    issuer — and the initiation request carries `client_id` so a tool can tell
    them apart. Doing that needs a rule for what happens when the caller names a
    client the issuer did not register, and E1 writes it with the multi-tenant
    work that needs it. Until then a second registration is a loud refusal
    instead of a silent choice between two.
    """
    if not issuer.strip():
        raise LaunchRefusedError(
            "The login initiation names no `iss`, so there is no platform to look up."
        )
    rows = list(session.execute(select(LtiPlatform).where(LtiPlatform.issuer == issuer)).scalars())
    if not rows:
        raise LaunchRefusedError(
            "No registration exists for the platform that began this launch. An administrator "
            "registers a platform before it can launch this tool (SPEC §2)."
        )
    if len(rows) > 1:
        raise LaunchRefusedError(
            "More than one registration exists for that platform, and this tool cannot yet tell "
            "which of them began the launch."
        )
    return rows[0]


def begin_a_launch(session: Session, settings: Settings, form: Mapping[str, str]) -> Initiation:
    """Turn a platform's login initiation into the authorization request it expects.

    The two hints go back exactly as they arrived. They are the platform's own
    opaque values — who is launching, and from which placement — and a tool that
    dropped either gets a launch for whoever the platform guesses, or none at
    all.

    **A registration that states no authorization endpoint is refused, not
    defaulted.** The column is nullable because a row written before E1-05 has no
    value for it, so NULL means "not stated" — and the answer to "not stated" is
    that an administrator completes the registration. A fallback to any
    process-wide address would be the finding E1-05 closes, re-opened under
    another name: one string standing in for every registration that does not
    carry its own.
    """
    platform = registered_platform(session, form.get("iss", ""))
    endpoint = (platform.authorization_endpoint or "").strip()
    if not endpoint:
        raise LaunchRefusedError(
            "That platform's registration states no authorization endpoint, so this tool does not "
            "know where to send the browser to continue the launch. An administrator completes the "
            "registration before it can launch this tool (SPEC §2)."
        )
    state = secrets.token_urlsafe(STATE_NONCE_BYTES)
    nonce = secrets.token_urlsafe(STATE_NONCE_BYTES)

    parameters = {
        **AUTHORIZATION_REQUEST_CONSTANTS,
        "client_id": platform.client_id,
        # Built from `PUBLIC_BASE_URL` and never from the incoming request. The
        # platform compares this exactly against the launch URL it registered, so
        # a value taken from the request's `Host` header or from its
        # `target_link_uri` would be a redirect URI the caller chose.
        "redirect_uri": f"{settings.public_base_url.rstrip('/')}{LAUNCH_PATH}",
        "state": state,
        "nonce": nonce,
    }
    for hint in ("login_hint", "lti_message_hint"):
        value = form.get(hint)
        if value:
            parameters[hint] = value

    return Initiation(
        parameters=parameters, state=state, nonce=nonce, authorization_endpoint=endpoint
    )


def registered_deployment(session: Session, platform: LtiPlatform, deployment_id: Any) -> None:
    """Refuse a launch from a placement this tool was never installed into.

    `lti_deployment` is a table nothing else in E0 reads, which is exactly why
    this check is the easiest of the seven to leave out: a tool that resolves the
    platform by `iss` and stops has a launch door that works for every test
    anybody writes. A deployment distinguishes one installation of a tool inside
    an LMS from another, and a launch naming an unregistered one came from a
    place nobody installed this tool.
    """
    if not isinstance(deployment_id, str) or not deployment_id:
        raise LaunchRefusedError(
            "The launch carries no `deployment_id` claim, so which installation of this tool it "
            "came from is not stated (LTI 1.3 core)."
        )
    found = session.execute(
        select(LtiDeployment.id).where(
            LtiDeployment.lti_platform_id == platform.id,
            LtiDeployment.deployment_id == deployment_id,
        )
    ).first()
    if found is None:
        raise LaunchRefusedError(
            "That platform has no deployment of this tool registered under the identifier the "
            "launch names."
        )


def verified_launch(
    session: Session,
    http: httpx.Client,
    form: Mapping[str, str],
    carried: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """The claims of a launch this tool is willing to act on.

    Everything downstream reads what this returns and never the token, so there
    is no path by which an unverified claim reaches a landing page.

    The order is deliberate. `state` is compared **first**, before anything is
    fetched or parsed, because it is the only check that costs nothing and it is
    what makes an unsolicited launch cheap to refuse. The issuer is resolved from
    the token's unverified claims next — which is not trust, it is the only way
    to find out whose key to check the signature with, and the signature check
    immediately afterwards is what binds the two together.
    """
    if carried is None:
        raise LaunchRefusedError(
            "This launch carries no login this tool started, so there is nothing to check its "
            "`state` and `nonce` against. It may simply have taken too long."
        )

    delivered_state = form.get("state") or ""
    expected_state = str(carried.get("state") or "")
    if not delivered_state or not expected_state:
        raise LaunchRefusedError("The launch carries no `state`, which every launch must return.")
    if not same_opaque_value(delivered_state, expected_state):
        raise LaunchRefusedError("The launch returns a `state` this tool did not issue.")

    token = form.get("id_token") or ""
    if not token:
        raise LaunchRefusedError("The launch carries no `id_token`, so there is nothing to verify.")

    # Unverified, and used for exactly one thing: choosing whose published key to
    # check the signature against. That is not a decision made on trust — a tool
    # cannot know which key to fetch without reading who claims to have signed,
    # and the signature check immediately below is what makes the claim true or
    # refuses it. Every claim any caller reads comes out of `verified_claims`.
    try:
        stated = jwt.decode(token, options={"verify_signature": False})
    except jwt.PyJWTError as failure:
        raise LaunchRefusedError("The launch's `id_token` is not a readable JWT.") from failure
    issuer = str(stated.get("iss") or "")

    platform = registered_platform(session, issuer)

    try:
        claims = verified_claims(
            http,
            token,
            jwks_url=platform.jwks_url,
            issuer=platform.issuer,
            audience=platform.client_id,
        )
    except TokenVerificationError as refusal:
        raise LaunchRefusedError(str(refusal)) from refusal

    expected_nonce = str(carried.get("nonce") or "")
    delivered_nonce = str(claims.get("nonce") or "")
    if not delivered_nonce or not expected_nonce:
        raise LaunchRefusedError("The launch carries no `nonce`, which every launch must return.")
    if not same_opaque_value(delivered_nonce, expected_nonce):
        raise LaunchRefusedError("The launch returns a `nonce` this tool did not send.")

    registered_deployment(session, platform, claims.get(DEPLOYMENT_ID_CLAIM))

    # `lti_platform.jwks_fetched_at` is deliberately left unwritten. It is the
    # column that would record a key-set fetch, and E0-18 caches no key set — so
    # writing it would record a fetch nothing ever reads, on a connection that
    # holds `SELECT` and no `UPDATE` (lti_registration_grants_v001.sql). The
    # ticket that adds caching writes it with the code that reads it.
    return claims
