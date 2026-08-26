"""Beginning an LTI 1.3 launch, and deciding whether the one that came back holds.

SPEC §7.3, §9.1, E1-08. ADR 0073 deferred `pylti1p3` to "the ticket that
restructures this code anyway"; this is that ticket, and the launch door now
validates on the library rather than by hand (`app.services.tokens` keeps the web
door). What E0-18 skipped and E1 owns is here: single-use nonces (a Postgres
ledger, `app.lti.replay_guard`), clock-skew windows, and state round-trip
integrity — with the survival of a launch inside a cookie-blocked LMS iframe left
to `app.services.session`.

**Two legs.** The platform's launch page posts an OIDC third-party-initiated
login to `/lti/login` carrying `iss`, `login_hint`, `target_link_uri` and
`lti_message_hint`; `begin_a_launch` runs `pylti1p3`'s `OIDCLogin`, which mints
the `state` and `nonce`, stores them in in-flight cookies (`app.lti.fastapi_adapter`)
and redirects to the platform's authorization endpoint. The platform answers by
posting a signed `id_token` back to `/lti/launch` with that `state`, and
`verified_launch` checks it.

**Each refusal is classified by which check failed, never by string-matching the
library's message.** `pylti1p3`'s `LtiException` interpolates the offending claim
value, so forwarding it to a page or a log is the exact leak SPEC §10 forbids.
Instead the validate steps are called individually and each failure is turned
into a fixed `LaunchRefusedError` subclass with its own constant, claim-free
message; the door logs only the subclass name. The order the checks run in is
this module's, chosen so that one deliberately-wrong launch (E1-07's mints) trips
exactly the guard it is named for.

**The algorithm list is a constant here** (ADR 0073's closing condition): the
launch signature is RS256 and the header's `alg` is checked against that constant
before the signature is verified, so an `alg: none` or an HMAC-with-the-public-key
confusion is refused by this module and never reaches a verifier that might read
`alg` off the token.

**The key set is fetched through `app.state.http`**, the repo's one httpx client,
the way `app.services.tokens` fetches the web door's — never through `pylti1p3`'s
own `requests` connection, which is unreachable from a test and bound by no
timeout this application sets. The fetched keys are handed to the launch, so the
library verifies against them without opening a second HTTP path.

**A refusal is a page, never a redirect** (open-redirector discipline, unchanged),
and never quotes what was sent.
"""

import logging
import time
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from pylti1p3.exception import LtiException, OIDCException
from pylti1p3.message_launch import MessageLaunch
from pylti1p3.oidc_login import OIDCLogin
from pylti1p3.redirect import Redirect
from pylti1p3.session import SessionService
from sqlalchemy.orm import Session

from app.config import Settings, is_development
from app.lti.fastapi_adapter import (
    CookieJar,
    FastApiCookieService,
    FastApiLaunchDataStorage,
    FastApiRedirect,
    FastApiRequest,
)
from app.lti.registration import MultipleRegistrationsError, OrmToolConf
from app.lti.replay_guard import NonceReplayedError, claim_nonce
from app.services.tokens import TokenVerificationError, key_set

__all__ = [
    "LAUNCH_PATH",
    "LOGIN_PATH",
    "AudienceRefused",
    "ClockSkewRefused",
    "DeploymentRefused",
    "IssuerRefused",
    "LaunchRefusedError",
    "MessageTypeRefused",
    "NonceRefused",
    "SignatureRefused",
    "StateRefused",
    "VersionRefused",
    "begin_a_launch",
    "verified_launch",
]

# Where this tool answers. Written here rather than in the router because the
# launch `redirect_uri` is built from `LAUNCH_PATH`, and the platform compares it
# exactly; two copies of a URL a platform compares exactly is `docs/MISTAKES.md`
# entry 13.
LOGIN_PATH = "/lti/login"
LAUNCH_PATH = "/lti/launch"

# The LTI 1.3 message claims this module reads, spelled as the specification
# spells them. A claim under any other name is a claim no conformant library
# reads.
LTI_CLAIM_PREFIX = "https://purl.imsglobal.org/spec/lti/claim/"
DEPLOYMENT_ID_CLAIM = f"{LTI_CLAIM_PREFIX}deployment_id"
MESSAGE_TYPE_CLAIM = f"{LTI_CLAIM_PREFIX}message_type"
VERSION_CLAIM = f"{LTI_CLAIM_PREFIX}version"

# The one message type this tool serves and the one LTI version it speaks. Deep
# Linking is out of scope (the epic README), so a `LtiDeepLinkingRequest` is a
# real message type this tool recognises as LTI and still refuses.
RESOURCE_LINK_MESSAGE_TYPE = "LtiResourceLinkRequest"
LTI_VERSION = "1.3.0"

# The only signature algorithm a launch may carry, checked against the token
# header before the signature is verified. A hardcoded constant, never read from
# the token or from configuration — ADR 0073's closing condition, applied to the
# adapter. RS256 is what the IMS security framework specifies for an LTI 1.3
# launch.
LAUNCH_SIGNATURE_ALGORITHMS = ("RS256",)

# How far a launch's `iat`/`exp` may sit outside this tool's clock and still be
# honoured. Five minutes covers ordinary machine-clock drift between a platform
# and this tool without honouring a token minted an hour early or expired an hour
# ago — the two `iat_future`/`exp_past` mints push their timestamps far past this.
CLOCK_SKEW_TOLERANCE_SECONDS = 300

# The lifetime of a claimed nonce in the replay ledger. A spent nonce need only
# be remembered for as long as the launch that spent it could be replayed; this
# is generous for a launch a browser delivers immediately.
NONCE_LEDGER_LIFETIME_SECONDS = 3600

# The one place in `app/lti/` that logs. One WARNING per refusal, carrying only
# the guard name — never a claim, a token, or a form value (SPEC §10, criterion
# 6). The web door and every downstream reader read `verified_launch`'s return
# value, never the token.
logger = logging.getLogger("app.lti.launch")


class LaunchRefusedError(Exception):
    """A launch cannot be admitted, and why in words a person can act on.

    Carries no claim value and no part of any token — a refusal reaches an HTML
    page and a log, and a launch token is a credential (SPEC §10). The subclasses
    below name which check refused; the door logs the subclass name and turns the
    message into a 4xx page.
    """


class SignatureRefused(LaunchRefusedError):  # noqa: N818 - the class name is the guard string the door logs and the refusal suite asserts
    """The signature, the algorithm, or the key that signed the launch did not hold."""


class AudienceRefused(LaunchRefusedError):  # noqa: N818 - the class name is the guard string the door logs and the refusal suite asserts
    """The launch was issued for a different tool than this one."""


class IssuerRefused(LaunchRefusedError):  # noqa: N818 - the class name is the guard string the door logs and the refusal suite asserts
    """No registration exists for the platform that began this launch."""


class NonceRefused(LaunchRefusedError):  # noqa: N818 - the class name is the guard string the door logs and the refusal suite asserts
    """The launch carries no `nonce`, or one this tool did not issue."""


class DeploymentRefused(LaunchRefusedError):  # noqa: N818 - the class name is the guard string the door logs and the refusal suite asserts
    """The launch names a deployment this tool was never installed into."""


class MessageTypeRefused(LaunchRefusedError):  # noqa: N818 - the class name is the guard string the door logs and the refusal suite asserts
    """The launch is a message type this tool does not serve."""


class VersionRefused(LaunchRefusedError):  # noqa: N818 - the class name is the guard string the door logs and the refusal suite asserts
    """The launch states an LTI version this tool does not speak."""


class StateRefused(LaunchRefusedError):  # noqa: N818 - the class name is the guard string the door logs and the refusal suite asserts
    """The launch returns a `state` this tool did not issue, or none at all."""


class ClockSkewRefused(LaunchRefusedError):  # noqa: N818 - the class name is the guard string the door logs and the refusal suite asserts
    """The launch was minted too far in the future, or expired too long ago."""


class _FastApiOIDCLogin(OIDCLogin):  # type: ignore[type-arg]
    """`pylti1p3`'s OIDC login, redirecting through this adapter's `Redirect`."""

    def get_redirect(self, url: str) -> Redirect[str]:
        return FastApiRedirect(url)


class _FastApiMessageLaunch(MessageLaunch):  # type: ignore[type-arg]
    """`pylti1p3`'s message launch, reading params off the parsed form."""

    def _get_request_param(self, key: str) -> str:
        return str(self._request.get_param(key))


def _adapter(
    form: Mapping[str, str], jar: CookieJar, settings: Settings
) -> tuple[FastApiRequest, FastApiCookieService, FastApiLaunchDataStorage]:
    """The three adapter objects a login or a launch is driven through."""
    request = FastApiRequest(form, jar_cookies(jar), secure=not is_development(settings))
    return request, FastApiCookieService(jar), FastApiLaunchDataStorage(jar)


def jar_cookies(jar: CookieJar) -> dict[str, str]:
    """The request cookies the jar holds, as the adapter request reads them."""
    return {name: jar.read(name) or "" for name in jar.incoming_names()}


def begin_a_launch(
    session: Session, settings: Settings, form: Mapping[str, str], jar: CookieJar
) -> str:
    """Turn a platform's login initiation into the authorization request it expects.

    Runs `pylti1p3`'s `OIDCLogin`: it resolves the registration (its client id and
    authorization endpoint), mints a fresh `state` and `nonce`, writes them to the
    in-flight cookies through `jar`, and returns the URL to redirect the browser
    to. The two hints go back exactly as they arrived — they are the platform's
    opaque values, and a tool that dropped either gets a launch for whoever the
    platform guesses, or none at all.

    A registration that does not exist, names more than one client, or states no
    authorization endpoint is refused rather than defaulted — the same guards
    E0-18 held, preserved through the adapter.
    """
    request, cookies, storage = _adapter(form, jar, settings)
    tool_conf = OrmToolConf(session)
    oidc = _FastApiOIDCLogin(request, tool_conf, SessionService(request), cookies, storage)
    launch_url = f"{settings.public_base_url.rstrip('/')}{LAUNCH_PATH}"
    try:
        redirect = oidc.get_redirect_object(launch_url)
    except OIDCException as refusal:
        raise IssuerRefused(
            "No registration exists for the platform that began this launch, or it did not carry "
            "the login hint a launch must. An administrator registers a platform before it can "
            "launch this tool (SPEC §2)."
        ) from refusal
    except MultipleRegistrationsError as conflict:
        raise IssuerRefused(str(conflict)) from conflict
    except AssertionError as incomplete:
        # `OIDCLogin` asserts the registration states an authorization endpoint;
        # a NULL one means the registration was never completed.
        raise IssuerRefused(
            "That platform's registration states no authorization endpoint, so this tool does not "
            "know where to send the browser to continue the launch. An administrator completes the "
            "registration before it can launch this tool (SPEC §2)."
        ) from incomplete
    return redirect.get_redirect_url()


def verified_launch(
    session: Session,
    http: httpx.Client,
    settings: Settings,
    form: Mapping[str, str],
    jar: CookieJar,
) -> dict[str, Any]:
    """The claims of a launch this tool is willing to act on, or a `LaunchRefusedError`.

    Everything downstream reads what this returns and never the token, so no
    unverified claim reaches a landing page. Each refusal is logged with the guard
    name alone and raised as a claim-free subclass.
    """
    try:
        return _validate(session, http, form, jar, settings)
    except NonceReplayedError as replay:
        logger.warning("NonceReplayedError")
        raise LaunchRefusedError(str(replay)) from replay
    except LaunchRefusedError as refusal:
        logger.warning(type(refusal).__name__)
        raise


def _validate(
    session: Session,
    http: httpx.Client,
    form: Mapping[str, str],
    jar: CookieJar,
    settings: Settings,
) -> dict[str, Any]:
    """Run the checks in order; raise the specific refusal the first failing one names.

    The claim is spent last (`claim_nonce`), only after every other check has
    passed, so a launch refused for any earlier reason leaves its nonce unspent
    and the legitimate retry open.
    """
    request, cookies, storage = _adapter(form, jar, settings)
    tool_conf = OrmToolConf(session)
    launch = _FastApiMessageLaunch(
        request, tool_conf, SessionService(request), cookies, launch_data_storage=storage
    ).set_auto_validation(False)
    # The signature step verifies the JWS only; audience, expiry and issued-at are
    # this module's own checks, so the library is told not to repeat them.
    launch.set_jwt_verify_options({"verify_aud": False, "verify_exp": False, "verify_iat": False})

    # 1. `state` round-trips — the cheapest check, refusing an unsolicited launch first.
    try:
        launch.validate_state()
    except LtiException as failure:
        raise StateRefused("The launch returns a `state` this tool did not issue.") from failure

    # 2. The token is a well-formed JWS this module can read the header and body of.
    try:
        launch.validate_jwt_format()
    except LtiException as failure:
        raise SignatureRefused("The launch's `id_token` is not a readable JWT.") from failure

    body = launch._jwt.get("body", {})
    header = launch._jwt.get("header", {})

    # 3. Clock skew, on the decoded (still unverified) claims — before the
    # signature, so an expired-but-validly-signed launch is refused for its clock
    # and not miscounted as a signature failure.
    _refuse_clock_skew(body)

    # 4. The `nonce` is one this tool issued at login (anti-injection). Single-use
    # is the replay ledger's job, at the end.
    try:
        launch.validate_nonce()
    except LtiException as failure:
        raise NonceRefused(
            "The launch carries no `nonce`, or one this tool did not send."
        ) from failure

    # 5. The issuer resolves to a registration, and the audience is that
    # registration's client. Resolved here rather than through the library's own
    # step so the two failures classify apart.
    registration = _resolve_registration(session, body)

    # 6. The algorithm is the one this tool pins, and the signature verifies
    # against the registration's published keys — fetched through the repo's httpx
    # client and handed to the launch, never through `pylti1p3`'s own connection.
    if header.get("alg") not in LAUNCH_SIGNATURE_ALGORITHMS:
        raise SignatureRefused(
            "The launch's `id_token` is signed with an algorithm this tool does not accept."
        )
    try:
        keys = dict(key_set(http, registration.get_key_set_url()))
    except TokenVerificationError as failure:
        # The key set could not be fetched or was not a usable JWK Set. The
        # message carries no address (`app.services.tokens`'s own discipline), and
        # this refusal carries none either — a refusal that named the server-side
        # key-set host would publish the tool's topology to whoever provoked it.
        raise SignatureRefused(
            "The launch could not be verified: the platform's key set could not be read."
        ) from failure
    registration.set_key_set(keys)
    launch._registration = registration
    try:
        launch.validate_jwt_signature()
    except LtiException as failure:
        raise SignatureRefused("The launch's signature did not verify.") from failure

    # 7. The deployment is one registered under this platform.
    _refuse_unregistered_deployment(session, body)

    # 8. The message type is one this tool serves.
    if body.get(MESSAGE_TYPE_CLAIM) != RESOURCE_LINK_MESSAGE_TYPE:
        raise MessageTypeRefused("The launch is a message type this tool does not serve.")

    # 9. The LTI version is the one this tool speaks.
    if body.get(VERSION_CLAIM) != LTI_VERSION:
        raise VersionRefused("The launch states an LTI version this tool does not speak.")

    # 10. Spend the nonce — single-use, and only now that everything else holds.
    claim_nonce(
        session,
        nonce=str(body["nonce"]),
        expires_at=datetime.now(UTC) + timedelta(seconds=NONCE_LEDGER_LIFETIME_SECONDS),
    )
    return dict(body)


def _refuse_clock_skew(body: Mapping[str, Any]) -> None:
    """Refuse a launch minted too far in the future or expired too long ago."""
    now = int(time.time())
    issued_at = body.get("iat")
    expires_at = body.get("exp")
    if not isinstance(issued_at, int) or not isinstance(expires_at, int):
        raise ClockSkewRefused(
            "The launch carries no readable `iat`/`exp`, so its age cannot be judged."
        )
    if issued_at > now + CLOCK_SKEW_TOLERANCE_SECONDS:
        raise ClockSkewRefused("The launch was minted too far in the future to be honoured.")
    if expires_at < now - CLOCK_SKEW_TOLERANCE_SECONDS:
        raise ClockSkewRefused("The launch expired too long ago to be honoured.")


def _resolve_registration(session: Session, body: Mapping[str, Any]) -> Any:
    """The `pylti1p3` registration for this launch's issuer and audience, or a refusal.

    `IssuerRefused` when no row registers the issuer (or more than one does, which
    this tool cannot yet tell apart), `AudienceRefused` when the launch's audience
    is not that registration's client — the two failures the library folds into
    one generic "registration not found".
    """
    issuer = str(body.get("iss") or "")
    tool_conf = OrmToolConf(session)
    try:
        registration = tool_conf.find_registration_by_issuer(issuer)
    except MultipleRegistrationsError as conflict:
        raise IssuerRefused(str(conflict)) from conflict
    if registration is None:
        raise IssuerRefused("No registration exists for the platform that began this launch.")

    audience = body.get("aud")
    client_id = audience[0] if isinstance(audience, list) else audience
    if client_id != registration.get_client_id():
        raise AudienceRefused("The launch was issued for a different tool than this one.")
    return registration


def _refuse_unregistered_deployment(session: Session, body: Mapping[str, Any]) -> None:
    """Refuse a launch from a placement this tool was never installed into."""
    deployment_id = body.get(DEPLOYMENT_ID_CLAIM)
    if not isinstance(deployment_id, str) or not deployment_id:
        raise DeploymentRefused(
            "The launch carries no `deployment_id`, so which installation of this tool it came "
            "from is not stated."
        )
    issuer = str(body.get("iss") or "")
    audience = body.get("aud")
    client_id = audience[0] if isinstance(audience, list) else audience
    tool_conf = OrmToolConf(session)
    deployment = tool_conf.find_deployment_by_params(issuer, deployment_id, str(client_id or ""))
    if deployment is None:
        raise DeploymentRefused(
            "That platform has no deployment of this tool registered under the identifier the "
            "launch names."
        )
