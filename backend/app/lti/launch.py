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
the `state` and `nonce`, and remembers the `state` -> `nonce` mapping
**server-side** (`app.lti.in_flight`) rather than in a cookie — so a launch inside
a cookie-blocked LMS iframe validates all the same (ADR 0089). Then it redirects
to the platform's authorization endpoint. The platform answers by posting a signed
`id_token` back to `/lti/launch` with that `state`, and `verified_launch` looks
the `state` up server-side, checks the `nonce` against it, and validates the rest.
Nothing about the handshake requires a third-party cookie (SPEC §7.3); the session
a valid launch issues is likewise cookieless (`app.services.session`).

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
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import parse_qsl, urlsplit

import httpx
from pylti1p3.exception import LtiException, OIDCException
from pylti1p3.message_launch import MessageLaunch
from pylti1p3.oidc_login import OIDCLogin
from pylti1p3.redirect import Redirect
from pylti1p3.session import SessionService
from sqlalchemy.orm import Session

from app.config import Settings, is_development
from app.lti.fastapi_adapter import (
    FastApiRedirect,
    FastApiRequest,
    NoOpCookieService,
    NoOpLaunchDataStorage,
)
from app.lti.in_flight import consume_launch, look_up_launch, remember_launch
from app.lti.registration import MultipleRegistrationsError, OrmToolConf
from app.lti.replay_guard import NonceReplayedError, claim_nonce
from app.services.tokens import TokenVerificationError, key_set

__all__ = [
    "INSTRUCTOR_ROLE_URI",
    "LAUNCH_PATH",
    "LEARNER_ROLE_URI",
    "LOGIN_PATH",
    "LTI_ROLES_CLAIM",
    "MEMBERSHIP_VOCABULARY",
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
    "stated_roles",
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

# The claim a launch states its roles in, and the LIS v2 membership vocabulary it
# draws them from. Not this project's to choose either: SPEC §7.3 asks for strict
# LTI 1.3 core, and a role compared under any other name is a role no conformant
# platform sends.
#
# **They live here since E1-13**, which deleted `app/services/landing.py` — the
# module that used to hold them and to turn a roles claim into a landing view.
# Nothing turns them into a view any more: which screen somebody opens on comes
# from the assignment model (`app.services.authz.resolve_landing`, ADR 0098).
# What still reads them, and lawfully, is SPEC §7.3's ingestion —
# `app.services.provisioning` asks whether a launch is a staff launch, and
# `app.services.roster_sync` asks which roster members teach — so they belong in
# the module §13 describes as "launch validation, role/context resolution".
#
# **`LEARNER_ROLE_URI` is read by nothing under `app/` today**, and is kept
# because a vocabulary held half here and half in whoever needs the other member
# is the drift `docs/MISTAKES.md` entry 13 is about: `INSTRUCTOR_ROLE_URI` means
# "this is a staff launch" at exactly one call site, and the constant naming its
# counterpart is what lets the next reader check that reading.
LTI_ROLES_CLAIM = f"{LTI_CLAIM_PREFIX}roles"
MEMBERSHIP_VOCABULARY = "http://purl.imsglobal.org/vocab/lis/v2/membership#"
INSTRUCTOR_ROLE_URI = f"{MEMBERSHIP_VOCABULARY}Instructor"
LEARNER_ROLE_URI = f"{MEMBERSHIP_VOCABULARY}Learner"

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

# How long an in-flight launch handshake is remembered before the daily purge may
# reclaim it. Five minutes, the same bound the retired login cookie had (ADR
# 0078): a login a browser follows completes at once, and a launch that has not
# come back in five minutes is not coming back.
IN_FLIGHT_LIFETIME_SECONDS = 300

# The one place in `app/lti/` that logs. One WARNING per refusal, carrying only
# the guard name — never a claim, a token, or a form value (SPEC §10, criterion
# 6). The web door and every downstream reader read `verified_launch`'s return
# value, never the token.
logger = logging.getLogger("app.lti.launch")


def stated_roles(claim: Any) -> tuple[str, ...]:
    """The role strings in a roles claim, whatever shape the issuer sent it in.

    LTI 1.3 makes this an array, and every conformant platform sends one. A single
    string is accepted because some platforms send one, and a claim of any other
    shape yields nothing rather than raising — an unusable claim and an absent
    claim lead the callers to the same answer, and that answer is theirs to make.

    **Here since E1-13**, with the vocabulary above; see the comment there for why
    the module that used to hold it is gone and who still reads it.
    """
    if isinstance(claim, str):
        return (claim,)
    if isinstance(claim, Sequence):
        return tuple(role for role in claim if isinstance(role, str))
    return ()


class LaunchRefusedError(Exception):
    """A launch cannot be admitted, and why in words a person can act on.

    Carries no claim value and no part of any token — a refusal reaches an HTML
    page and a log, and a launch token is a credential (SPEC §10). The subclasses
    below name which check refused; the door logs the subclass name and turns the
    message into a 4xx page.
    """

    def __init__(self, *args: object, guard: str | None = None) -> None:
        super().__init__(*args)
        self._guard = guard

    @property
    def guard(self) -> str:
        """The machine-readable name of the guard that refused (ADR 0103).

        The class name for every subclass below, because the class *is* the
        guard vocabulary. The one exception is the nonce-ledger replay, which is
        wrapped in a bare `LaunchRefusedError` (`NonceReplayedError` is not one
        of these subclasses) and names the wrapped guard here instead — so the
        `data-reason` marker on the refusal page and the WARNING in the log agree.
        """
        return self._guard if self._guard is not None else type(self).__name__


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
    form: Mapping[str, str], settings: Settings
) -> tuple[FastApiRequest, NoOpCookieService, NoOpLaunchDataStorage]:
    """The three adapter objects `pylti1p3` requires, the cookie/storage inert.

    The launch handshake is validated against `app.lti.in_flight`, not through
    `pylti1p3`'s state cookie and nonce storage, so those two are no-ops here — see
    the adapter module. Only the request (the parsed form) carries anything real.
    """
    request = FastApiRequest(form, secure=not is_development(settings))
    return request, NoOpCookieService(), NoOpLaunchDataStorage()


def begin_a_launch(session: Session, settings: Settings, form: Mapping[str, str]) -> str:
    """Turn a platform's login initiation into the authorization request it expects.

    Runs `pylti1p3`'s `OIDCLogin` to resolve the registration (its client id and
    authorization endpoint), mint a fresh `state` and `nonce`, and build the
    redirect URL. Then it records the `state` -> `nonce` mapping **server-side**
    (`app.lti.in_flight.remember_launch`) rather than in a cookie, so the launch
    can validate it even inside a cookie-blocked iframe (ADR 0089). The caller
    commits the write. The two hints go back exactly as they arrived.

    A registration that does not exist, names more than one client, or states no
    authorization endpoint is refused rather than defaulted — the same guards
    E0-18 held, preserved through the adapter.
    """
    request, cookies, storage = _adapter(form, settings)
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

    url = redirect.get_redirect_url()
    # The `state` and `nonce` `OIDCLogin` minted are in the authorization request's
    # query; read them back and remember the mapping server-side.
    params = dict(parse_qsl(urlsplit(url).query))
    remember_launch(
        session,
        state=params.get("state", ""),
        nonce=params.get("nonce", ""),
        expires_at=datetime.now(UTC) + timedelta(seconds=IN_FLIGHT_LIFETIME_SECONDS),
    )
    return url


def verified_launch(
    session: Session,
    http: httpx.Client,
    settings: Settings,
    form: Mapping[str, str],
) -> dict[str, Any]:
    """The claims of a launch this tool is willing to act on, or a `LaunchRefusedError`.

    Everything downstream reads what this returns and never the token, so no
    unverified claim reaches a landing page. Each refusal is logged with the guard
    name alone and raised as a claim-free subclass, **and consumes the in-flight
    `state`** — a `state` is good once, so one that led to a refusal is deleted and
    a correct `state` replayed after a refusal finds nothing and is refused. A
    *successful* launch does not consume its `state`: the replay of a whole valid
    launch is caught by the nonce ledger, which is where single-use of a spent
    launch belongs. The caller commits either way.
    """
    delivered_state = form.get("state") or ""
    try:
        return _validate(session, http, form, settings, delivered_state)
    except NonceReplayedError as replay:
        guard = type(replay).__name__
        logger.warning(guard)
        consume_launch(session, state=delivered_state)
        raise LaunchRefusedError(str(replay), guard=guard) from replay
    except LaunchRefusedError as refusal:
        logger.warning(type(refusal).__name__)
        consume_launch(session, state=delivered_state)
        raise


def _validate(
    session: Session,
    http: httpx.Client,
    form: Mapping[str, str],
    settings: Settings,
    delivered_state: str,
) -> dict[str, Any]:
    """Run the checks in order; raise the specific refusal the first failing one names.

    The claim is spent last (`claim_nonce`), only after every other check has
    passed, so a launch refused for any earlier reason leaves its nonce unspent
    and the legitimate retry open.
    """
    request, cookies, storage = _adapter(form, settings)
    tool_conf = OrmToolConf(session)
    launch = _FastApiMessageLaunch(
        request, tool_conf, SessionService(request), cookies, launch_data_storage=storage
    ).set_auto_validation(False)
    # The signature step verifies the JWS only; audience, expiry and issued-at are
    # this module's own checks, so the library is told not to repeat them.
    launch.set_jwt_verify_options({"verify_aud": False, "verify_exp": False, "verify_iat": False})

    # 1. A `state` is present at all — the cheapest check, refusing an unsolicited
    # launch first (an absent `state` is `missing_state`).
    if not delivered_state:
        raise StateRefused("The launch carries no `state`, which every launch must return.")

    # 2. The token is a well-formed JWS this module can read the header and body of.
    try:
        launch.validate_jwt_format()
    except LtiException as failure:
        raise SignatureRefused("The launch's `id_token` is not a readable JWT.") from failure

    body = launch._jwt.get("body", {})
    header = launch._jwt.get("header", {})

    # 3. The `state` names a launch this tool started and is still holding — read
    # server-side (`app.lti.in_flight`), never from a cookie, so a cookie-blocked
    # iframe validates all the same (ADR 0089). The expected `nonce` comes back
    # with it. A `state` this tool never issued, or one already consumed by a
    # refusal, is `tampered_state`/unsolicited.
    expected_nonce = look_up_launch(session, state=delivered_state, now=datetime.now(UTC))
    if expected_nonce is None:
        raise StateRefused("The launch returns a `state` this tool did not issue.")

    # 4. The token carries the `nonce` this tool is expecting for that `state`
    # (anti-injection). Single-use of a spent launch is the replay ledger's job, at
    # the end.
    token_nonce = body.get("nonce")
    if not token_nonce:
        raise NonceRefused("The launch carries no `nonce`, which every launch must return.")
    if str(token_nonce) != expected_nonce:
        raise NonceRefused("The launch returns a `nonce` this tool did not send.")

    # 5. Clock skew, on the decoded (still unverified) claims — before the
    # signature, so an expired-but-validly-signed launch is refused for its clock
    # and not miscounted as a signature failure.
    _refuse_clock_skew(body)

    # 6. The issuer resolves to a registration, and the audience is that
    # registration's client. Resolved here rather than through the library's own
    # step so the two failures classify apart.
    registration = _resolve_registration(session, body)

    # 7. The algorithm is the one this tool pins, and the signature verifies
    # against the registration's published keys — fetched through the repo's httpx
    # client and handed to the launch, never through `pylti1p3`'s own connection.
    _refuse_unpinned_algorithm(header)
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

    # 8. The deployment is one registered under this platform.
    _refuse_unregistered_deployment(session, body)

    # 9. The message type is one this tool serves.
    if body.get(MESSAGE_TYPE_CLAIM) != RESOURCE_LINK_MESSAGE_TYPE:
        raise MessageTypeRefused("The launch is a message type this tool does not serve.")

    # 10. The LTI version is the one this tool speaks.
    if body.get(VERSION_CLAIM) != LTI_VERSION:
        raise VersionRefused("The launch states an LTI version this tool does not speak.")

    # 11. Spend the nonce — single-use, and only now that everything else holds.
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


def _refuse_unpinned_algorithm(header: Mapping[str, Any]) -> None:
    """Refuse a launch whose JWS header names an algorithm this tool does not pin.

    ADR 0073's closing condition, applied to the adapter: the accepted algorithm
    is a hardcoded constant here (`LAUNCH_SIGNATURE_ALGORITHMS`), never read from
    the token or from configuration, so an `alg: none` or an HMAC-with-the-public-
    key confusion is refused by this module before the signature is verified.

    **This is defence in depth, and a small standalone unit on purpose.**
    `pylti1p3`'s own key/algorithm matching independently refuses both of those
    today — its `get_public_key` only accepts a key whose `alg` matches the
    header's, and the platform publishes RS256 keys — so end-to-end the two guards
    agree and mutating this one alone leaves the integration tests green. Pulling
    the pin into its own function is what lets it be exercised directly, so a break
    in *this* guard is caught here rather than masked by the library's.
    """
    if header.get("alg") not in LAUNCH_SIGNATURE_ALGORITHMS:
        raise SignatureRefused(
            "The launch's `id_token` is signed with an algorithm this tool does not accept."
        )


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
