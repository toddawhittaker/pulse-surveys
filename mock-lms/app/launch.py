"""What a tool's authorization request must carry, and the claims it gets back.

This is the platform half of the LTI 1.3 launch, and it is the half E0-14 owns.
The tool's half — validating what comes out of here against a registration,
against a remembered `state` and a remembered `nonce`, against a clock-skew
window — is E1's, and the ticket says so: "The mock produces launches; validating
them is E1's work."

**The order of the protocol, since the two endpoints are easy to confuse.** The
launch page posts an OIDC third-party-initiated login request to the *tool's*
login-initiation URL, carrying `iss`, `login_hint` and `target_link_uri`. Neither
`state` nor `nonce` exists at that point. The tool then makes an authorization
request back to *this* platform, and it is the tool that mints both values: the
platform echoes `state` on the way back and puts `nonce` inside the `id_token`.
That is what this module does.

**Nothing here is lenient.** A mock that shrugged at a missing `nonce`, an
unregistered `redirect_uri` or a client ID it does not know would be a mock that
lets E1 ship a tool with the same holes and never notice — E0-14's security
review asks exactly that no shortcut here becomes a habit E1 inherits. So every
request is refused with a reason naming the parameter, and the refusal is a 400
rather than a redirect, because redirecting an error to an address that failed
validation is how an open redirector is built.
"""

import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from app.config import PlatformSettings
from app.seed import COURSE_SECTION_TYPE, MockPlacement, MockUser, SeededPlatform

# The LTI 1.3 message claims, spelled as the specification spells them. A claim
# under any other name is a claim `pylti1p3` (SPEC §7.1) will not read.
LTI_CLAIM_PREFIX = "https://purl.imsglobal.org/spec/lti/claim/"
MESSAGE_TYPE_CLAIM = f"{LTI_CLAIM_PREFIX}message_type"
VERSION_CLAIM = f"{LTI_CLAIM_PREFIX}version"
DEPLOYMENT_ID_CLAIM = f"{LTI_CLAIM_PREFIX}deployment_id"
TARGET_LINK_URI_CLAIM = f"{LTI_CLAIM_PREFIX}target_link_uri"
RESOURCE_LINK_CLAIM = f"{LTI_CLAIM_PREFIX}resource_link"
CONTEXT_CLAIM = f"{LTI_CLAIM_PREFIX}context"
ROLES_CLAIM = f"{LTI_CLAIM_PREFIX}roles"

# A plain resource-link launch, which SPEC §7.3 makes the default. Deep Linking
# is explicitly out of scope for E0-14.
RESOURCE_LINK_MESSAGE_TYPE = "LtiResourceLinkRequest"

# The exact string LTI 1.3 fixes. Not `1.3`, not `1.3.1`.
LTI_VERSION = "1.3.0"

# How long an issued `id_token` is good for. Five minutes is what the IMS
# security framework suggests for a launch token, and E0-14 sets no lifetime, so
# this is a constant rather than a setting: there is one correct answer and a knob
# for it would only ever be turned to a wrong one.
TOKEN_LIFETIME_SECONDS = 300

# What the OIDC implicit flow the LTI 1.3 security framework uses requires a tool
# to send. `response_mode` is the one this platform will not merely check but
# cannot vary from: `form_post` is what LTI specifies, and it is the only shape
# the authorization response below is written in.
REQUIRED_SCOPE = "openid"
REQUIRED_RESPONSE_TYPE = "id_token"
REQUIRED_RESPONSE_MODE = "form_post"


class AuthorizationRequestError(ValueError):
    """A tool's authorization request cannot be answered, and why.

    Carries a prose reason rather than an OIDC error code, because the audience
    is whoever is debugging a launch at eleven at night and the reason is what
    they need. The route turns it into a 400.
    """


@dataclass(frozen=True)
class ResolvedLaunch:
    """One authorization request, checked, with the seeded rows it names."""

    user: MockUser
    placement: MockPlacement
    roles: tuple[str, ...]
    state: str
    nonce: str
    redirect_uri: str


def required(parameters: Mapping[str, Any], name: str) -> str:
    """One parameter that must be present and non-empty, or a refusal naming it."""
    value = str(parameters.get(name) or "").strip()
    if not value:
        raise AuthorizationRequestError(
            f"The authorization request carries no `{name}`. It carries {sorted(parameters)}."
        )
    return value


def resolve_launch(
    parameters: Mapping[str, Any],
    settings: PlatformSettings,
    platform: SeededPlatform,
) -> ResolvedLaunch:
    """Check a tool's authorization request and find the launch it asks for.

    Every check below is one a real platform makes, and each has a failure mode
    worth naming:

    - **`client_id`** identifies the registration. A platform that signed for a
      client it has never heard of issues tokens no tool can place.
    - **`redirect_uri`** must be one this platform has registered. Without that
      check the endpoint will post a signed `id_token` to any address a caller
      names, which is an open redirector with a credential attached.
    - **`state`** is the tool's cross-site request forgery defence and **`nonce`**
      is its replay defence. Both are the tool's values; a platform that invents
      either breaks the tool's check in a way that reads as a tool bug.
    - **the enrollment** decides the roles. Resolving it from the seed rather than
      from the request is what stops the caller choosing its own role, which is
      the whole difference between a mock platform and a signing oracle.
    """
    scope = required(parameters, "scope")
    if REQUIRED_SCOPE not in scope.split():
        raise AuthorizationRequestError(
            f"The authorization request asks for scope {scope!r}, which does not include "
            f"{REQUIRED_SCOPE!r}. An LTI 1.3 launch is an OpenID Connect authentication request."
        )

    response_type = required(parameters, "response_type")
    if response_type != REQUIRED_RESPONSE_TYPE:
        raise AuthorizationRequestError(
            f"The authorization request asks for `response_type` {response_type!r}. The LTI 1.3 "
            f"security framework specifies the implicit flow, {REQUIRED_RESPONSE_TYPE!r}."
        )

    # Absent means the OIDC default for this response type, which is `fragment`
    # — and that is not what LTI uses, so absence is answered with `form_post`
    # rather than refused. A different value *is* refused: this platform serves
    # one shape and would otherwise claim to serve another.
    response_mode = str(parameters.get("response_mode") or REQUIRED_RESPONSE_MODE).strip()
    if response_mode != REQUIRED_RESPONSE_MODE:
        raise AuthorizationRequestError(
            f"The authorization request asks for `response_mode` {response_mode!r}. LTI 1.3 "
            f"returns the `id_token` by {REQUIRED_RESPONSE_MODE!r}, which is the only shape this "
            "platform answers in."
        )

    client_id = required(parameters, "client_id")
    if client_id != settings.client_id:
        raise AuthorizationRequestError(
            f"No registration for `client_id` {client_id!r}. This platform is registered for "
            f"{settings.client_id!r}."
        )

    redirect_uri = required(parameters, "redirect_uri")
    if redirect_uri != settings.tool_launch_url:
        raise AuthorizationRequestError(
            f"`redirect_uri` {redirect_uri!r} is not registered for this tool. The registered "
            f"one is {settings.tool_launch_url!r}. A platform that posts a signed `id_token` to "
            "an unregistered address is an open redirector."
        )

    state = required(parameters, "state")
    nonce = required(parameters, "nonce")

    login_hint = required(parameters, "login_hint")
    user = platform.user(login_hint)
    if user is None:
        raise AuthorizationRequestError(
            f"No seeded user for `login_hint` {login_hint!r}. The seeded users are "
            f"{sorted(seeded.user_id for seeded in platform.users)}."
        )

    message_hint = required(parameters, "lti_message_hint")
    placement = platform.placement(message_hint)
    if placement is None:
        raise AuthorizationRequestError(
            f"No seeded placement for `lti_message_hint` {message_hint!r}. The seeded "
            f"placements are {sorted(seeded.resource_link_id for seeded in platform.placements)}."
        )

    roles = platform.roles(user.user_id, placement.context.context_id)
    if roles is None:
        raise AuthorizationRequestError(
            f"{user.user_id!r} is not enrolled in {placement.context.context_id!r}, so there is "
            "no launch to sign. Roles come from the enrollment, never from the request."
        )

    return ResolvedLaunch(
        user=user,
        placement=placement,
        roles=roles,
        state=state,
        nonce=nonce,
        redirect_uri=redirect_uri,
    )


def id_token_claims(
    launch: ResolvedLaunch,
    settings: PlatformSettings,
    issued_at: int | None = None,
) -> dict[str, Any]:
    """The `id_token` payload: the JWT envelope first, then the LTI message.

    `aud` is the client ID as a single string, not a list containing it. OpenID
    Connect requires an `azp` claim as soon as the audience holds more than one
    value, and a launch is for one tool — a list here would be a shape a
    conformant tool has to reject for a reason that has nothing to do with this
    launch.

    `exp` is `iat` plus a lifetime rather than a lifetime subtracted from
    anything, which sounds like a silly thing to say until you have debugged a
    token that was expired the moment it was minted and read it as the tool's
    clock-skew handling being broken.
    """
    issued = int(time.time()) if issued_at is None else issued_at
    context = launch.placement.context
    context_claim: dict[str, Any] = {
        "id": context.context_id,
        "label": context.label,
        "type": [COURSE_SECTION_TYPE],
    }
    if context.title is not None:
        context_claim["title"] = context.title

    return {
        "iss": settings.issuer,
        "sub": launch.user.user_id,
        "aud": settings.client_id,
        "nonce": launch.nonce,
        "iat": issued,
        "exp": issued + TOKEN_LIFETIME_SECONDS,
        MESSAGE_TYPE_CLAIM: RESOURCE_LINK_MESSAGE_TYPE,
        VERSION_CLAIM: LTI_VERSION,
        DEPLOYMENT_ID_CLAIM: settings.deployment_id,
        TARGET_LINK_URI_CLAIM: settings.tool_launch_url,
        RESOURCE_LINK_CLAIM: {
            "id": launch.placement.resource_link_id,
            "title": launch.placement.title,
        },
        CONTEXT_CLAIM: context_claim,
        ROLES_CLAIM: list(launch.roles),
    }
