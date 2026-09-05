"""Assignment and Grade Services 2.0, from the tool's side: one line item and one score (E3-04).

SPEC §3.4 gives every section one gradebook column called "Pulse Participation"
and posts a percentage into it whenever a recomputation changes the value. This
module is the protocol half of that and nothing else: it finds or creates the
column, and it posts one student's score to it. **What** to post, and **when**, is
E3-06's; the client is handed a percentage, a ledger and a timestamp and carries
them.

**The conformance shape is `app.services.roster_sync`'s, copied deliberately.**
That module is this tool's other LTI Advantage client and it solved the same four
problems: the transport arrives as a constructor argument, redirects are off, a
fetched address is judged before it is dialled and the connection is pinned to
the address that was judged, and the registration comes from the section's own
deployment. Each of those is repeated below with a docstring naming its sibling.
The one thing shared rather than repeated is `PinnedResolutionAdapter`, because it
is a security control and two copies of one are two places for it to drift
(`docs/MISTAKES.md` entry 13). ADR 0132 records the choice and what it leaves
open.

**The outbound transport is a parameter, and it has to be.** In a test neither
the mock platform's advertised address nor this tool's own resolves over a
network, so a client that built its own `requests.Session` internally could not be
driven against a platform by any test at all — no token exchange to inspect, no
`Authorization` header to read. In production nobody passes one and a plain
session is built here. `app.services.roster_sync`'s module docstring makes the
same argument at length.

**A token per scope, never a union.** AGS 2.0 defines four scopes and this client
asks for exactly the one the call it is about to make needs: a container read asks
for the read-only line-item scope, a create asks for the writing one, a score post
asks for the score scope, and a result read asks for the result scope. A tool that
asked for all four at once would present a credential opening every route on every
call, and the platform's own per-route rule would then be measuring nothing.

**There is no retry and no backoff here, and that is a decision** (ADR 0132). One
attempt per HTTP call, exactly as the roster sync makes one attempt per page: the
scheduled sweep is the retry mechanism, and for grades that sweep is E3-06's. What
an operator sees of a failing post is the `ags_call` row — the URL, the status, the
instant and the section (SPEC §6.1) — and a NULL status there has exactly one
meaning, that the call never reached the platform (ADR 0129).

**A 409 stops rather than retries.** AGS answers 409 when the platform holds a
score newer than the one being posted, so a retry cannot succeed and a loop
against a platform under load is a loop against every section at once. The client
reads back what the platform holds for that user and raises `AgsConflictError`
carrying it, so the caller has a fact rather than a guess (ADR 0052).

**The score string, the ledger and the timestamp are carried, never re-derived.**
Each is a value the caller handed over and each reaches the platform byte for
byte. ADR 0052's retry identity rests on it: a value the poster re-derives is not
provably the value it is retrying, and `61.5`, `61.50` and `0.615` are one number
and three strings.

**Nothing here logs a score, a ledger line or an LMS user id**, and nothing writes
one into `ags_call`. A worker's log stream is read by whoever is on call and kept
longer than any table in this system; a participation figure against a student's
`sub` there is a statement about a named person's standing, outside every read
path SPEC §4.1 governs.

**This module persists nothing to `section` and commits nothing.** Find-or-create
answers the line item and leaves storing it to its caller, and the caller owns the
transaction exactly as it does for the roster sync. That caller is
`app.services.grading.ensure_line_item`, which holds the `grade_passback` sanction
and the column-scoped grant E3-05 spends (ADR 0136) and judges the answered
address again before writing it down.
"""

import json
import logging
import re
from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from typing import Any, Final
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import UUID, uuid4

import requests
from pylti1p3.exception import LtiServiceException
from pylti1p3.service_connector import ServiceConnector
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import DEVELOPMENT_ENVIRONMENT, Settings, url_host
from app.lti.platforms import profile_for
from app.lti.platforms.base import PlatformProfile
from app.lti.registration import NoSigningKeyError, OrmToolConf
from app.models.lti import (
    AGS_CONTAINER_ADDRESS_COLUMN,
    AGS_LINE_ITEM_ADDRESS_COLUMN,
    AgsCall,
    LtiDeployment,
    LtiPlatform,
    RegistrationAddressError,
    refuse_invalid_fetched_address,
)
from app.models.org import Section
from app.services.roster_sync import PinnedResolutionAdapter

__all__ = [
    "AgsCallError",
    "AgsConflictError",
    "AgsError",
    "find_or_create_line_item",
    "post_score",
]

logger = logging.getLogger("app.lti.ags")

# The four scopes AGS 2.0 names, as the specification spells them. A tool asks its
# token endpoint for the exact string the launch's service claim advertises, so a
# spelling of this tool's own devising is a token no platform grants.
LINE_ITEM_SCOPE: Final[str] = "https://purl.imsglobal.org/spec/lti-ags/scope/lineitem"
LINE_ITEM_READONLY_SCOPE: Final[str] = (
    "https://purl.imsglobal.org/spec/lti-ags/scope/lineitem.readonly"
)
RESULT_READONLY_SCOPE: Final[str] = "https://purl.imsglobal.org/spec/lti-ags/scope/result.readonly"
SCORE_SCOPE: Final[str] = "https://purl.imsglobal.org/spec/lti-ags/scope/score"

# The media types AGS 2.0 fixes. Sent rather than `application/json` because a
# platform is entitled to content-negotiate on them, and a tool that asked for
# `application/json` would be asking for a document the specification does not
# describe.
LINE_ITEM_MEDIA_TYPE: Final[str] = "application/vnd.ims.lis.v2.lineitem+json"
LINE_ITEM_CONTAINER_MEDIA_TYPE: Final[str] = "application/vnd.ims.lis.v2.lineitemcontainer+json"
RESULT_CONTAINER_MEDIA_TYPE: Final[str] = "application/vnd.ims.lis.v2.resultcontainer+json"
SCORE_MEDIA_TYPE: Final[str] = "application/vnd.ims.lis.v1.score+json"

# How this tool recognises its own gradebook column, and what it calls it.
#
# **`resourceId` is the identity and the label is not** (ADR 0133). An instructor
# renaming a column is an ordinary thing to do and it must not produce a second
# one on the next run; `resourceId` is the member AGS 2.0 provides for a tool's
# own key, it is filterable on the container, and nothing in an LMS invites a
# person to edit it. The label is what a person reads in their own gradebook.
PULSE_RESOURCE_ID: Final[str] = "pulse-participation"
PULSE_LABEL: Final[str] = "Pulse Participation"

# What a "Pulse Participation" column this tool creates is scored out of. SPEC
# §3.4 posts a percentage, so a hundred is the denominator that makes the number
# in the gradebook the number in the ledger. It is a **default and not a
# guarantee**: an instructor can re-point a column's points in every LMS in the
# sector, and every score this client posts is out of the maximum it read off the
# line item rather than out of this (ADR 0051).
PULSE_SCORE_MAXIMUM: Final[int] = 100

# The AGS members this client reads and writes, spelled as AGS 2.0 spells them.
RESOURCE_ID_MEMBER: Final[str] = "resourceId"
LABEL_MEMBER: Final[str] = "label"
SCORE_MAXIMUM_MEMBER: Final[str] = "scoreMaximum"
LINE_ITEM_ID_MEMBER: Final[str] = "id"

# AGS 2.0 derives the Score and Result services from a line item's own `id` by
# adding a path segment to it. The **path**, before any query the id carries: see
# `_service_address` below for what concatenation does instead.
SCORES_SEGMENT: Final[str] = "scores"
RESULTS_SEGMENT: Final[str] = "results"

# The container filter AGS 2.0 defines on `resourceId`, and the page-size
# parameter. A platform is free to ignore either, so the walk matches on
# `resourceId` itself and follows `rel="next"` to the end whatever comes back.
RESOURCE_ID_FILTER: Final[str] = "resource_id"
LIMIT_PARAMETER: Final[str] = "limit"

# How many pages of one container this tool will follow before it gives up. **A
# bound on somebody else's header** rather than a page budget, exactly as
# `app.services.roster_sync::MAX_PAGES_WALKED` is: the `Link` relation a walk
# follows is composed by the platform, so a header that advertises a next page for
# ever is a worker that never finishes and an `ags_call` table that never stops
# growing. A section's gradebook holds a handful of columns, so a hundred pages is
# far past anything real.
MAX_PAGES_WALKED: Final[int] = 100

# How long a single outbound call to a platform may take before it gives up, as a
# `requests` `(connect, read)` pair. `ensure_line_item` holds `SELECT … FOR UPDATE`
# on the section row across every call this client makes to create a line item, so
# a platform that completes the TCP handshake and then never answers would hold
# that row lock, the database connection and the worker slot without bound — and on
# the single default queue that also stalls `reclassify_floored_comments`, so
# §3.3's floored safety verdicts stop arriving. `requests`' own default is `None`,
# which waits forever, so the bound is set here rather than inherited.
#
# The connect bound sits just over three seconds so it is longer than the doubled
# TCP SYN retransmit a healthy but momentarily busy host can take, and the read
# bound is ten seconds: an AGS create or a container page is a small document, and a
# platform that has accepted the connection and not answered a small body in ten
# seconds is one this tool gives up on rather than one it waits out. Neither is a
# retry — there is none here (ADR 0132) — so the number is a ceiling on one attempt.
AGS_REQUEST_TIMEOUT: Final[tuple[float, float]] = (3.05, 10.0)

# The link relation a paged container advertises its next page under (RFC 8288 §3)
# and the name of the header carrying it.
NEXT_RELATION: Final[str] = "next"
LINK_HEADER: Final[str] = "link"

# One `<url>` of an RFC 8288 `Link` header with the parameters belonging to it.
# **A second copy of `app.services.roster_sync::LINK_HEADER_ENTRY`**, which carries
# the full argument for why this tool reads the header itself rather than taking
# `pylti1p3`'s answer for it: that library lower-cases the whole header before
# matching, which breaks a platform paging on a case-sensitive cursor, and it
# requires `rel` to be a link's first parameter with a quoted value, which RFC 8288
# makes neither. A header it misses ends a walk early **as complete**.
#
# The duplication is deliberate and is the smaller of two evils here: the roster's
# copy is private to a service module, and importing a private name across a module
# boundary is the thing this ticket was told not to do. Rehoming the pair so both
# clients read one parser is proposed in this ticket's pull request rather than
# taken, because it crosses a module boundary.
LINK_HEADER_ENTRY: Final[re.Pattern[str]] = re.compile(
    r"""<(?P<url>[^>]*)>                    # the URI-reference, opaque between the brackets
        (?P<parameters>                     # its parameters, up to the next link
            (?: \s*;                        # each one introduced by a semicolon
                (?: [^,;"] | "(?:[^"\\]|\\.)*"? )*   # bare text, or a quoted-string
            )*
        )""",
    re.VERBOSE,
)

# RFC 8259's `number`, anchored. What it is for is the score: the caller hands a
# canonical percentage **string** and this client puts that string on the wire
# unchanged (ADR 0052), which means the string is written into a JSON document
# without going through a serialiser. So it is checked against JSON's own grammar
# first — a value that is not a number literal is refused loudly rather than
# composed into a body, because a string interpolated into JSON is a string that
# can write the document's own syntax.
JSON_NUMBER: Final[re.Pattern[str]] = re.compile(
    r"-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?"
)


class AgsError(RuntimeError):
    """This section's gradebook could not be reached, or answered something unusable.

    The base of this module's three, so a caller that only wants to know whether
    the post happened can catch one name. Raised rather than logged for the
    conditions that are true of the *deployment* rather than of one section — no
    registration behind the section's deployment, no tool signing key — because
    every section in the institution has the same problem and a client that
    swallowed it would leave an operator reading a product full of sections whose
    grades silently never post.
    """


class AgsCallError(AgsError):
    """One HTTP call to a platform's AGS service did not succeed.

    `status` is what the platform answered, or `None` where the call never reached
    it at all. That is the same distinction `ags_call.response_code` keeps (ADR
    0129) and it is the one an operator acts on: a refusal is a registration
    problem and a silence is a network one.
    """

    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class AgsConflictError(AgsError):
    """The platform holds a score newer than the one posted, and here is what it holds.

    AGS 2.0's 409 (ADR 0052). It is the one 4xx that says retrying cannot work, so
    this is raised instead of a retry and it carries the Result the platform served
    for that user — the re-read is there so that "the platform holds something
    newer" is a fact the caller can act on rather than a guess.

    Typed, and defined here rather than taken from the transport, because a caller
    deciding whether to record a grade as sent cannot branch on an `HTTPError`: it
    is indistinguishable from every other failure a post can have.

    **`held` is on the attribute and never in the message**, and the split is the
    point rather than tidiness. An error's `str()` is what every logger prints —
    a caller writing `logger.exception(...)`, a task runner rendering an
    unhandled exception — so a message carrying the Result would put a named
    student's grade into a log stream through a line nobody wrote. The message
    names the section and the column; the attribute is read only by a caller that
    asked for it. `None` where the re-read itself could not be made.
    """

    def __init__(self, message: str, *, held: Any = None) -> None:
        super().__init__(message)
        self.held = held


# ---------------------------------------------------------------------------
# The entry points.
# ---------------------------------------------------------------------------


def find_or_create_line_item(
    session: Session,
    section_id: UUID,
    http: requests.Session | None = None,
    settings: Settings | None = None,
    resolve: Callable[[str], Sequence[str]] | None = None,
) -> Mapping[str, Any]:
    """The section's "Pulse Participation" line item, created if the gradebook holds none.

    ADR 0133 fixes the order, and each step exists because the one before it can
    legitimately fail:

      1. **The id the section already holds**, fetched rather than believed. A
         client that answered with the stored string has established nothing — the
         column may have been deleted in the LMS since — and a client that walked
         the container every time pays a paged read per section per posting run and
         matches on `resourceId` where it should have matched on the id.
      2. **The container, matched on `resourceId`**, when there is no stored id or
         the platform no longer serves it. Never on the label: an instructor
         renaming the column is ordinary, and a label match would meet it as "no
         Pulse column here" and create a second one every run.
      3. **A create**, when the container holds none.

    Answers the line-item document exactly as the platform served it. **Nothing is
    written to `section`**, so a caller that wants the id kept stores it itself —
    `app.services.grading.ensure_line_item` is the one that does, under the
    sanction and the column grant ADR 0136 records.

    `http` is the transport every outbound call travels over — see the module
    docstring for why it is a parameter. `settings` supplies the environment the
    fetched-address rules are judged under, and `resolve` is the resolution seam
    those rules take (ADR 0101); both default to values built here, so a caller that
    has neither passes neither.
    """
    settings = Settings() if settings is None else settings
    section, container = _gradebook_of(session, section_id)
    call = _Caller(session, section, container, http, settings, resolve)

    stored = section.ags_line_item_url
    if stored is not None:
        held = _stored_line_item(call, stored)
        if held is not None:
            return held

    walked = _walked_container(call)
    found = next(
        (item for item in walked if item.get(RESOURCE_ID_MEMBER) == PULSE_RESOURCE_ID), None
    )
    if found is not None:
        logger.info(
            "section %s: the platform's line-item container already carries the %r column, so "
            "none was created",
            section_id,
            PULSE_RESOURCE_ID,
        )
        call.judged_line_item(_line_item_id(found))
        return found
    return _created_line_item(call)


def post_score(
    session: Session,
    section_id: UUID,
    *,
    user_id: str,
    score: str,
    ledger: str,
    timestamp: str,
    line_item: Mapping[str, Any],
    http: requests.Session | None = None,
    settings: Settings | None = None,
    resolve: Callable[[str], Sequence[str]] | None = None,
) -> None:
    """Post one student's participation score to `line_item`, exactly as it was handed over.

    `user_id` is the platform's own subject string for the student, `score` the
    canonical percentage string, `ledger` the per-week ledger SPEC §3.4 puts in the
    AGS `comment` member, and `timestamp` the RFC 3339 instant naming the
    *recomputation* rather than the attempt. All four go on the wire unchanged.

    **`timestamp` is a string rather than a `datetime`, and the reason is the same
    one that keeps `score` a string.** ADR 0052 makes a retry the identical body
    re-sent, and identical means byte-identical: a value round-tripped through a
    `datetime` comes back spelled however this tool renders it, so `+00:00` becomes
    `Z` and a platform recording what it received records a different document from
    the one the first attempt sent. The caller owns the spelling.

    **The maximum is the line item's own** (ADR 0051), read off the document rather
    than assumed to be `PULSE_SCORE_MAXIMUM`. A hundred is right for every column
    this client creates and wrong for every one it finds after somebody re-pointed
    it, and a platform that refuses the mismatch rather than rescaling — which is
    what the specification lets it do and what this tool's own mock does — answers
    422 to a client holding a constant.

    Answers nothing. A post that did not happen raises: `AgsConflictError` where
    the platform holds something newer, `AgsCallError` otherwise.
    """
    settings = Settings() if settings is None else settings
    section, container = _gradebook_of(session, section_id)
    call = _Caller(session, section, container, http, settings, resolve)

    identifier = _line_item_id(line_item)
    call.judged_line_item(identifier)
    profile = profile_for(call.platform.issuer)
    body = _score_document(
        user_id=user_id,
        score=score,
        ledger=ledger,
        timestamp=timestamp,
        maximum=_line_item_maximum(line_item),
        profile=profile,
    )
    address = _service_address(identifier, SCORES_SEGMENT)
    answered = call.made(
        SCORE_SCOPE,
        address,
        method="POST",
        body=body,
        content_type=SCORE_MEDIA_TYPE,
        accept=SCORE_MEDIA_TYPE,
    )
    if answered.status_code == 409:
        # Read once and used twice. A second read would be a second HTTP call, a
        # second `ags_call` row and a second chance for the platform to answer
        # something different — and the message and the attribute would then be
        # describing two states.
        held = call.held_result(identifier, user_id)
        # The message names the section and the column and stops there; what the
        # platform holds rides on the attribute. An error's `str()` is the thing
        # every logger prints — a caller writing `logger.exception(...)`, a task
        # runner rendering an unhandled exception — and the held Result is one
        # student's grade, so a message carrying it is a per-student disclosure
        # nobody decided to make. An attribute is read only by a caller that
        # asked for it.
        raise AgsConflictError(
            f"the platform answered 409 for a score posted to {address} for section {section_id}, "
            "which AGS 2.0 uses for a score older than the one it already holds for that student "
            "on that column. No retry was made — a 409 is the one refusal a retry cannot fix — and "
            "what the platform holds is on this error's `held` attribute.",
            held=held,
        )
    if not answered.ok:
        raise AgsCallError(
            f"the platform answered {answered.status_code} for a score posted to {address}. The "
            "score was not recorded and no retry was made; the scheduled sweep is what tries again.",
            status=answered.status_code,
        )
    logger.info(
        "section %s: a score was accepted by the platform at %s (%s)",
        section_id,
        address,
        answered.status_code,
    )


# ---------------------------------------------------------------------------
# One section's gradebook, and whose credentials reach it.
# ---------------------------------------------------------------------------


def _gradebook_of(session: Session, section_id: UUID) -> tuple[Section, str]:
    """The section and the line-item container address a launch stored on it.

    Both refusals are loud. A section that has been deleted since a job was
    enqueued is a condition to see rather than a gradebook to call; a section that
    carries no container address has never had a launch advertise one, and calling
    a URL that is not there is not something to attempt quietly.
    """
    section = session.get(Section, section_id)
    if section is None:
        raise AgsError(
            f"there is no section {section_id} to post a grade for. A job enqueued for a section "
            "that has since been deleted is a condition to see rather than a gradebook to call."
        )
    container = section.lms_ags_line_items_url
    if container is None:
        raise AgsError(
            f"section {section_id} carries no `{AGS_CONTAINER_ADDRESS_COLUMN}`, so no launch has "
            "advertised a gradebook for it and there is no line-item container to reach. A "
            "platform that withholds the AGS claim even from a staff launch leaves the section "
            "with no gradebook, which is a state rather than a fault."
        )
    return section, container


def _platform_for(session: Session, section: Section) -> LtiPlatform:
    """The registration this section was discovered through, and the only one.

    A copy of `app.services.roster_sync::_platform_for`, which carries the same
    argument for the roster: `section.lti_deployment_id → lti_deployment →
    lti_platform`, and nothing else. A context identifier is unique inside one
    registration and meaningless across registrations (ADR 0091), so the
    registration that discovered a section is the only one whose credentials mean
    anything at its gradebook — and a resolver that took whichever registration it
    found first would sign an assertion audienced at one platform and present the
    resulting token to another institution's gradebook, both halves of which are
    silent.
    """
    platform = session.scalars(
        select(LtiPlatform)
        .join(LtiDeployment, LtiDeployment.lti_platform_id == LtiPlatform.id)
        .where(LtiDeployment.id == section.lti_deployment_id)
    ).one_or_none()
    if platform is None:
        raise AgsError(
            f"section {section.id} is bound to deployment {section.lti_deployment_id}, which "
            "resolves to no registered platform. A section is bound to the registration it was "
            "discovered through, and without one there are no credentials to post its grades with."
        )
    return platform


def _registration_for(session: Session, platform: LtiPlatform) -> Any:
    """The `pylti1p3` registration for one platform row, ready to sign with.

    A copy of `app.services.roster_sync::_registration_for`. `OrmToolConf` is the
    one construction path this tool has for a registration, so the inbound door and
    both outbound clients resolve the same signing key and a platform verifying any
    of them sees the same key; which key that is, once a rotation can be in
    progress, is `app.lti.registration.current_signing_key` (ADR 0127).

    Both refusals are loud because they are facts about the *deployment* rather
    than about one section: a registration with no token endpoint and a tool with
    no signing key both mean nothing can be posted anywhere.
    """
    registration = OrmToolConf(session).find_registration_by_params(
        platform.issuer, platform.client_id
    )
    if registration is None or registration.get_auth_token_url() is None:
        raise AgsError(
            f"the registration for issuer {platform.issuer!r} states no token endpoint, so no "
            "access token can be requested and no grade can be posted. E1-05 adds "
            "`auth_token_url` to `lti_platform`; a registration written before it states none."
        )
    if registration.get_tool_private_key() is None:
        raise NoSigningKeyError(
            "This deployment holds no signing key that has not been retired, so there is nothing "
            "to sign a `client_assertion` with and no platform will issue this tool a token. "
            "`python scripts/signing_key.py generate` supplies one (ADR 0126), and retiring the "
            "last live key reaches this state too (ADR 0127)."
        )
    return registration


class _BoundedTransport(requests.Session):
    """A `requests.Session` that dials under `AGS_REQUEST_TIMEOUT` unless a caller sets its own.

    This client bounds the AGS calls it makes itself, explicitly, on the
    `self.transport.request(...)` at the foot of `_Caller.made`. The call it does
    *not* make itself is the token grant that precedes each of them:
    `pylti1p3`'s `ServiceConnector.get_access_token` posts to the auth endpoint
    over this same session with no `timeout`, and `ensure_line_item` holds the
    section's row lock across it — so a token endpoint that completes the handshake
    and then stalls holds that lock, the connection and the worker slot without
    bound exactly as a stalled AGS call would.

    Wrapping `pylti1p3` is the one thing this integration is told not to do, so the
    bound is set on the session it dials through instead: any request that names no
    `timeout` of its own — the token `POST` is the only one in this client — gets
    `AGS_REQUEST_TIMEOUT`. A caller that passes a `timeout` keeps it, which is why
    the explicit bound on the AGS call still reads exactly as written.

    Built only where this client builds its own transport, which is production; a
    test that injects a session drives its own object and the explicit bound on the
    AGS call is what holds there.
    """

    def request(self, *args: Any, **keywords: Any) -> requests.Response:
        keywords.setdefault("timeout", AGS_REQUEST_TIMEOUT)
        return super().request(*args, **keywords)


def _no_redirects(http: requests.Session | None) -> requests.Session:
    """The transport this client fetches over, with redirect-following turned off.

    A copy of `app.services.roster_sync::_no_redirects` in its redirect argument: a
    redirect is the same bypass as a hostile line-item id arriving one step
    earlier, because the address `refuse_invalid_fetched_address` judged is not the
    address the request ends at. `requests` has no session-level
    `allow_redirects`, so `max_redirects = 0` is the lever that reaches every call
    — any 30x then raises `TooManyRedirects`, a `RequestException`, which is
    recorded as a call this tool would not make.

    **Where this copy diverges from the roster's**: the session this client builds
    for itself is a `_BoundedTransport`, so the token grant `pylti1p3` posts over it
    is bounded too (see that class). The roster sync has the same unbounded token
    dial and is out of this ticket's scope; it is named in E3-05's pull request.
    """
    session = _BoundedTransport() if http is None else http
    session.max_redirects = 0
    return session


def _pinned(
    http: requests.Session, pins: Mapping[str, str], unpinned_hosts: set[str]
) -> requests.Session:
    """Mount `PinnedResolutionAdapter` over whatever this session already answers with.

    A copy of `app.services.roster_sync::_pinned`, over the roster's own adapter
    class rather than a second one: the pin closes a DNS-rebinding window between
    the moment an address is judged and the moment it is dialled, and a security
    control with two implementations is a control with one of them out of date
    (`docs/MISTAKES.md` entry 13).

    A session already carrying one of these is re-wrapped around its *inner*
    adapter rather than around the whole thing, so a caller that drives several
    sections over one session does not build a chain of wrappers each holding a pin
    table belonging to a section already posted to.
    """
    for scheme in ("https://", "http://"):
        held = http.get_adapter(scheme)
        inner = held.inner if isinstance(held, PinnedResolutionAdapter) else held
        http.mount(scheme, PinnedResolutionAdapter(inner, pins, unpinned_hosts))
    return http


class _Caller:
    """One section's AGS conversation: whose credentials, over what, judged how.

    Assembled once per entry point rather than per call, for the reason
    `sync_all_rosters` builds its connector inside the per-section function: a
    connector built once for several sections would present the first platform's
    credentials to every gradebook after it.

    The pin table is shared by reference with the adapter that reads it, so an
    address judged here is already pinned by the time the next request leaves.
    `unpinned_hosts` is the small set this client dials without a pin on purpose —
    the token endpoint, which `pylti1p3` calls and this client never judges, and in
    development the section's own gradebook host, which is the operator's. The
    adapter fails closed on any other pin miss.
    """

    def __init__(
        self,
        session: Session,
        section: Section,
        container: str,
        http: requests.Session | None,
        settings: Settings,
        resolve: Callable[[str], Sequence[str]] | None,
    ) -> None:
        self.session = session
        self.section_id = section.id
        self.container = container
        self.settings = settings
        self.resolve = resolve
        self.pins: dict[str, str] = {}
        self.unpinned_hosts: set[str] = set()
        self.transport = _pinned(_no_redirects(http), self.pins, self.unpinned_hosts)

        self.platform = _platform_for(session, section)
        self.registration = _registration_for(session, self.platform)
        token_host = url_host(self.registration.get_auth_token_url() or "")
        if token_host is not None:
            self.unpinned_hosts.add(token_host)
        exempt = url_host(container)
        if exempt is not None and settings.environment == DEVELOPMENT_ENVIRONMENT:
            self.unpinned_hosts.add(exempt)
        self.exempt_host = exempt
        self.connector = ServiceConnector(self.registration, requests_session=self.transport)

    # -- judging an address before it is dialled -----------------------------

    def judged(self, column: str, address: str) -> None:
        """Refuse `address` unless this container may fetch it, and pin what it resolved to.

        The roster sync's rule, applied to the two addresses this client fetches: the
        container a launch advertised, and every line-item id a platform answers
        with. Both are chosen by the *platform* at run time and both are dialled with
        the tool's own Bearer token attached, so a compromised one points this
        container at a loopback listener or at the cloud metadata service.

        **A refusal is recorded against the section's stored container address, and
        the refused address appears in the log line only.** A URL the platform chose,
        written into a record that SPEC §6.1 puts on an operator's console, is a
        second channel — and a row keyed to an attacker's string is also detached
        from the section whose gradebook history is being read.
        """
        try:
            resolved = refuse_invalid_fetched_address(
                self.settings.environment,
                column=column,
                address=address,
                resolve=self.resolve,
                development_exempt_host=self.exempt_host,
            )
        except RegistrationAddressError as refusal:
            _record_call(self.session, self.section_id, self.container, None)
            logger.warning(
                "section %s was told to fetch %s, which this container refuses: %s. No call was "
                "made and the refusal is recorded against the section's own stored gradebook "
                "address.",
                self.section_id,
                address,
                refusal,
            )
            raise AgsCallError(
                f"the address {address} is one this container refuses to fetch: {refusal}"
            ) from refusal
        host = url_host(address)
        if resolved and host is not None and host not in self.pins:
            self.pins[host] = resolved[0]

    def judged_line_item(self, identifier: str) -> None:
        """Judge one line-item id — stored, listed or just created — before addressing it."""
        self.judged(AGS_LINE_ITEM_ADDRESS_COLUMN, identifier)

    def judged_container(self, address: str) -> None:
        """Judge the container's first page, or a `rel="next"` the platform advertised."""
        self.judged(AGS_CONTAINER_ADDRESS_COLUMN, address)

    # -- one HTTP call, recorded whatever it answers -------------------------

    def made(
        self,
        scope: str,
        url: str,
        *,
        method: str = "GET",
        body: str | None = None,
        content_type: str | None = None,
        accept: str = "application/json",
        recorded: str | None = None,
    ) -> requests.Response:
        """Make one authorised call, leave one `ags_call` row, and answer the response.

        **The token comes from the connector and the request goes over the
        connector's own transport**, rather than through
        `ServiceConnector.make_service_request`, and there are two reasons. That
        method discards the status code, which is the whole of what `ags_call`
        records and which ADR 0129 gives a specific meaning; and its `Link` reader
        is the one `app.services.roster_sync` documents as wrong in two ways. What
        it does that matters — request a token with a tool-signed assertion and
        attach it — is `get_access_token`, which is called here. There is no
        unauthenticated path in this client to fall back to.

        `recorded` is the URL the row carries where that differs from the URL
        dialled. It differs in exactly one place: a Result read filtered to one
        student carries that student's `sub` in its query string, and settled
        decision 5 keeps a user id out of this table.

        **So `row_url` is the only address this method writes down, logs or puts
        in an error, and the dialled `url` is never any of those.** That is the
        whole redaction and it is stated as an invariant rather than left to each
        branch to remember: `row_url` is the caller's redacted address where one
        was given and the dialled address otherwise, so a caller that adds a
        second person-bearing query has one place to redact it.

        **Nothing here interpolates a transport exception's text**, for the same
        reason. `requests` builds a `ConnectionError` whose message quotes the URL
        it could not reach — the dialled one, query and all — so a warning handed
        `%s` of the failure puts a student's `sub` into a log stream through a
        string nobody wrote it into. The failure's class name says which kind of
        transport fault it was, which is what an operator reads, and the original
        travels on as the `__cause__` for a debugger.

        A refused token is recorded **against the AGS address with the token
        endpoint's status**, which is the roster's rule (ADR 0095) and E3-02's
        model docstring: the row is this section's record of an attempted call and
        SPEC §6.1's console reads it per section, so a row filed under the
        platform's OAuth surface would be a row about something the reader is not
        asking about. The status is the token endpoint's because a NULL there means
        one thing only — that nothing answered — and "these credentials were
        refused" and "nothing answered" are the two failures an operator has to
        tell apart.
        """
        row_url = url if recorded is None else recorded
        try:
            token = self.connector.get_access_token([scope])
        except LtiServiceException as refusal:
            answered = _answered_status(refusal)
            _record_call(self.session, self.section_id, row_url, answered)
            logger.warning(
                "the token endpoint answered %s for section %s, so no call was made to %s: this "
                "deployment's credentials were refused rather than its gradebook service",
                answered,
                self.section_id,
                row_url,
            )
            raise AgsCallError(
                f"the token endpoint answered {answered}, so no call was made to {row_url}",
                status=answered,
            ) from refusal
        except requests.RequestException as failure:
            _record_call(self.session, self.section_id, row_url, None)
            logger.warning(
                "no access token could be obtained for section %s (%s), so no call was made to %s",
                self.section_id,
                type(failure).__name__,
                row_url,
            )
            raise AgsCallError(
                f"no access token could be obtained ({type(failure).__name__}), so no call was "
                f"made to {row_url}"
            ) from failure

        headers = {"Authorization": f"Bearer {token}", "Accept": accept}
        if body is not None and content_type is not None:
            headers["Content-Type"] = content_type
        try:
            answered_call = self.transport.request(
                method, url, data=body, headers=headers, timeout=AGS_REQUEST_TIMEOUT
            )
        except requests.RequestException as failure:
            _record_call(self.session, self.section_id, row_url, None)
            logger.warning(
                "section %s could not reach %s at all (%s)",
                self.section_id,
                row_url,
                type(failure).__name__,
            )
            raise AgsCallError(
                f"{row_url} could not be reached ({type(failure).__name__})"
            ) from failure
        _record_call(self.session, self.section_id, row_url, answered_call.status_code)
        return answered_call

    def held_result(self, identifier: str, user_id: str) -> Any:
        """What the platform currently holds for one student on one line item, or `None`.

        The re-read a 409 triggers (ADR 0052). AGS 2.0's own `user_id` filter is
        used rather than the whole container, because a tool that asked a platform
        for the class and kept one row is holding grades it did not ask for.

        That filter puts the student's `sub` in a query string, which is a value
        SPEC §10 keeps out of a log; so the `ags_call` row is written against the
        unfiltered container address, and nothing here logs the URL it dialled.

        A read that itself fails answers `None`. The 409 is what the caller is being
        told about, and a client that turned a failed diagnostic read into a second
        failure would replace a precise error with a vague one.
        """
        address = _service_address(identifier, RESULTS_SEGMENT)
        try:
            answered = self.made(
                RESULT_READONLY_SCOPE,
                _with_query(address, {"user_id": user_id}),
                accept=RESULT_CONTAINER_MEDIA_TYPE,
                recorded=address,
            )
        except AgsError:
            return None
        if not answered.ok:
            return None
        try:
            return answered.json()
        except ValueError:
            return None


# ---------------------------------------------------------------------------
# Find or create, and the walk behind it.
# ---------------------------------------------------------------------------


def _stored_line_item(call: _Caller, stored: str) -> Mapping[str, Any] | None:
    """The line item at the id the section holds, or `None` if the platform will not serve it.

    `None` rather than a raise, and ADR 0133 is why: an id the platform no longer
    serves is what a column deleted or re-keyed in the LMS looks like, and it is a
    state to recover from by walking the container. A client that raised here would
    stop posting for that section for the rest of the term.
    """
    call.judged_line_item(stored)
    try:
        answered = call.made(LINE_ITEM_READONLY_SCOPE, stored, accept=LINE_ITEM_MEDIA_TYPE)
    except AgsCallError:
        logger.info(
            "section %s: the line-item id it holds could not be read, so the container will be "
            "walked instead",
            call.section_id,
        )
        return None
    if not answered.ok:
        logger.info(
            "section %s: the platform answered %s for the line-item id it holds, so the container "
            "will be walked instead",
            call.section_id,
            answered.status_code,
        )
        return None
    document = _document(answered, "line item")
    return document if isinstance(document, Mapping) else None


def _walked_container(call: _Caller) -> list[Mapping[str, Any]]:
    """Every line item the section's container serves, following `rel="next"` to the end.

    The container is asked with AGS 2.0's own `resourceId` filter, because a
    platform that honours it answers a one-item page instead of a gradebook. A
    platform is free to ignore it, so the caller matches on `resourceId` itself and
    this walk follows the header wherever it goes — the filter is an optimisation
    and never the rule.

    A walk that revisits a page, or that never says stop, is reported rather than
    followed: a `Link` header composed by the platform is somebody else's loop.
    """
    profile = profile_for(call.platform.issuer)
    following: str | None = _with_query(
        call.container,
        {RESOURCE_ID_FILTER: PULSE_RESOURCE_ID, LIMIT_PARAMETER: profile.container_page_size},
    )
    walked: set[str] = set()
    items: list[Mapping[str, Any]] = []
    while following is not None:
        if following in walked or len(walked) >= MAX_PAGES_WALKED:
            raise AgsCallError(
                f"the line-item container for section {call.section_id} advertised a page it had "
                f"already served, or never stopped advertising one, after {len(walked)} page(s). A "
                "container this tool cannot read to the end is one it cannot say holds no Pulse "
                "column, and creating one on that basis is how a section gets a second gradebook "
                "column every run."
            )
        call.judged_container(following)
        walked.add(following)
        answered = call.made(
            LINE_ITEM_READONLY_SCOPE, following, accept=LINE_ITEM_CONTAINER_MEDIA_TYPE
        )
        if not answered.ok:
            raise AgsCallError(
                f"the line-item container at {following} answered {answered.status_code}, so this "
                "tool cannot tell whether the section already has a Pulse column.",
                status=answered.status_code,
            )
        served = _document(answered, "line-item container")
        items.extend(item for item in _container_items(served) if isinstance(item, Mapping))
        following = _next_page_url(answered.headers)
    return items


def _created_line_item(call: _Caller) -> Mapping[str, Any]:
    """Create the section's "Pulse Participation" column and answer what the platform stored.

    The three members ADR 0133 fixes, and each is load-bearing. `resourceId` is
    what every later run matches on, so a column created without one is a column
    the next run cannot find and duplicates. The label is what a person reads.
    `scoreMaximum` is 100 because SPEC §3.4 posts a percentage, and a platform that
    refuses a disagreeing maximum rather than rescaling (ADR 0051) turns a column
    created out of anything else into one no participation score can ever reach.
    """
    body = json.dumps(
        {
            LABEL_MEMBER: PULSE_LABEL,
            SCORE_MAXIMUM_MEMBER: PULSE_SCORE_MAXIMUM,
            RESOURCE_ID_MEMBER: PULSE_RESOURCE_ID,
        }
    )
    answered = call.made(
        LINE_ITEM_SCOPE,
        call.container,
        method="POST",
        body=body,
        content_type=LINE_ITEM_MEDIA_TYPE,
        accept=LINE_ITEM_MEDIA_TYPE,
    )
    if not answered.ok:
        raise AgsCallError(
            f"the platform answered {answered.status_code} for a line item created in the "
            f"container at {call.container}, so section {call.section_id} has no gradebook column "
            "to post to.",
            status=answered.status_code,
        )
    created = _document(answered, "created line item")
    if not isinstance(created, Mapping):
        raise AgsCallError(
            f"the platform answered a {type(created).__name__} for a line item created in the "
            "container, and AGS 2.0 makes a line item a JSON object whose `id` is its own URL."
        )
    logger.info(
        "section %s: a %r gradebook column was created, out of %s",
        call.section_id,
        PULSE_RESOURCE_ID,
        PULSE_SCORE_MAXIMUM,
    )
    call.judged_line_item(_line_item_id(created))
    return created


# ---------------------------------------------------------------------------
# Reading a document, and composing one.
# ---------------------------------------------------------------------------


def _document(answered: requests.Response, subject: str) -> Any:
    """One AGS response body as JSON, or a refusal naming what could not be read."""
    try:
        return answered.json()
    except ValueError as unreadable:
        raise AgsCallError(
            f"the platform answered {answered.status_code} for a {subject} with a body that is not "
            f"JSON ({unreadable})."
        ) from unreadable


def _container_items(served: Any) -> Sequence[Any]:
    """The line items in a container document, however the platform wrapped them.

    AGS 2.0 serves an array. Some platforms wrap it in an object under
    `lineItems`, so both are read — a wrapper read as "no line items" is a
    container this tool believes empty, and it creates a second column on a
    gradebook that already has one.

    A `list` and nothing else, deliberately. `str` and `bytes` are `Sequence`s
    too, so a platform answering a bare string where a container belongs would be
    read as a container of one line item per character — a shape no assertion
    about "there is no Pulse column here" could see, and one that ends in a
    duplicate gradebook column.
    """
    if isinstance(served, Mapping):
        wrapped = served.get("lineItems")
        return wrapped if isinstance(wrapped, list) else []
    return served if isinstance(served, list) else []


def _line_item_id(line_item: Mapping[str, Any]) -> str:
    """A line item's own URL, or a refusal saying it has none."""
    identifier = line_item.get(LINE_ITEM_ID_MEMBER)
    if not isinstance(identifier, str) or not identifier:
        raise AgsCallError(
            f"the line item carries no `{LINE_ITEM_ID_MEMBER}`. AGS 2.0 makes it the platform's own "
            "URL for the column, and it is the address every score is derived from."
        )
    return identifier


def _line_item_maximum(line_item: Mapping[str, Any]) -> Any:
    """The maximum a line item is scored out of, read off the platform's own document.

    Never defaulted to `PULSE_SCORE_MAXIMUM`: ADR 0051 posts against the column's
    own maximum, and a client that filled in a default here would be posting a
    number out of a denominator the platform disagrees with.
    """
    maximum = line_item.get(SCORE_MAXIMUM_MEMBER)
    if not isinstance(maximum, int | float) or isinstance(maximum, bool):
        raise AgsCallError(
            f"the line item states `{SCORE_MAXIMUM_MEMBER}` {maximum!r}, which is not a number, so "
            "there is no denominator to post a percentage against (ADR 0051)."
        )
    return maximum


def _score_document(
    *,
    user_id: str,
    score: str,
    ledger: str,
    timestamp: str,
    maximum: Any,
    profile: PlatformProfile,
) -> str:
    """One AGS score, as the JSON text that goes on the wire.

    **The text rather than a dictionary, because `scoreGiven` has to arrive
    exactly as the caller spelled it.** `61.5` and `61.50` are one float and two
    strings, so a value round-tripped through a JSON decoder and re-encoded is not
    provably the value being retried (ADR 0052) — and a JSON serialiser is
    precisely a thing that re-spells a number. So the caller's string is placed
    into the document itself.

    Placed, and not interpolated: the score is checked against RFC 8259's own
    number grammar first, because a string written into a JSON document unchecked
    is a string that can write the document's syntax. A unique marker stands in for
    it while the rest of the document is serialised normally, and the marker's
    quoted form is replaced once — a marker that appeared any other number of times
    is a refusal rather than a substitution nobody meant.

    The ledger is carried by the serialiser as an ordinary JSON string, which is
    lossless: a decoder gives back the newlines it was handed. SPEC §3.4 puts the
    per-week ledger in the AGS `comment` member, and since v1 ships no view of the
    participation score that comment is the only place the arithmetic behind a
    posted percentage is visible to anybody (ADR 0125).

    The two progress members come from the platform profile on every post, never
    from a constant here (SPEC §7.3). That is what makes the seam a seam rather
    than a file the code never reads.
    """
    if not JSON_NUMBER.fullmatch(score):
        raise AgsError(
            f"the score handed to this client is {score!r}, which is not a JSON number. A "
            "participation percentage reaches the platform as the exact string it was computed as "
            "(ADR 0052), so anything that is not a number literal is refused here rather than "
            "written into a request body."
        )
    marker = uuid4().hex
    text = json.dumps(
        {
            "userId": user_id,
            "timestamp": timestamp,
            "scoreGiven": marker,
            "scoreMaximum": maximum,
            "activityProgress": profile.activity_progress,
            "gradingProgress": profile.grading_progress,
            "comment": ledger,
        }
    )
    quoted = json.dumps(marker)
    if text.count(quoted) != 1:
        raise AgsError(
            "the placeholder this client uses to carry a score string onto the wire appeared "
            f"{text.count(quoted)} times in the body it composed, so the substitution below would "
            "change something other than the score. Nothing was posted."
        )
    return text.replace(quoted, score)


def _service_address(identifier: str, segment: str) -> str:
    """A line item's Score or Result service, derived from its `id` **as a URL**.

    AGS 2.0 derives both by adding a path segment to the line item's own `id`, and
    every worked example in the specification shows an id that is a bare path — so
    `id + "/scores"` is right forever against a platform whose ids carry no query,
    and wrong the moment one does. Moodle's look like
    `…/lineitems/3/lineitem?type_id=1`, and concatenation there produces
    `…/lineitem?type_id=1/scores`: a request to the **line item itself** with a
    nonsense query. It is well formed, it is answerable, and it posts no score
    anywhere.

    So the segment goes on the path and the query is left where it is. A trailing
    slash does not become a doubled one, because a `//` in a path is a different
    path and a platform is free to mint either spelling.
    """
    split = urlsplit(identifier)
    path = f"{split.path.rstrip('/')}/{segment.strip('/')}"
    return urlunsplit((split.scheme, split.netloc, path, split.query, split.fragment))


def _with_query(url: str, parameters: Mapping[str, Any]) -> str:
    """`url` with `parameters` added to whatever query it already carries.

    A parameter of the same name is replaced rather than appended, so a container
    address that already names a `limit` cannot end up naming two — a URL whose
    meaning depends on which one the reader takes first.

    `keep_blank_values=True` on the parse, because an empty value is a value: a
    container filtered by `?tag=` and rebuilt without it is a different request.
    """
    split = urlsplit(url)
    held = [
        (name, value)
        for name, value in parse_qsl(split.query, keep_blank_values=True)
        if name not in parameters
    ]
    held.extend((name, str(value)) for name, value in parameters.items())
    return urlunsplit((split.scheme, split.netloc, split.path, urlencode(held), split.fragment))


def _next_page_url(headers: Mapping[str, Any]) -> str | None:
    """The next page a container's `Link` header advertises, spelled as it was sent.

    A copy of `app.services.roster_sync::_next_page_url`, which carries the full
    argument. Four rules, all RFC 8288 §3's: a link's parameters are unordered, so
    `rel` is looked for among all of them; a `rel` value is a token that may be
    bare and may name several relations; a header may carry several links, so each
    is read and only the one declaring `next` is followed; and a quoted parameter
    value is one value whatever it contains, so a `rel=next` written inside some
    other parameter's quoted text is that value's content and not a relation the
    platform declared.

    The URL is handed back byte for byte. Nothing is lower-cased, unescaped or
    resolved against the page it came from: what a platform put between the angle
    brackets is what it will answer to, and a relative reference is left to
    `refuse_invalid_fetched_address` to refuse rather than guessed at here.
    """
    header = next(
        (value for name, value in headers.items() if str(name).lower() == LINK_HEADER), None
    )
    if not isinstance(header, str) or not header:
        return None
    for entry in LINK_HEADER_ENTRY.finditer(header.replace("\n", " ")):
        for parameter in _split_outside_quotes(entry.group("parameters"), ";"):
            name, _, value = parameter.partition("=")
            if name.strip().lower() != "rel":
                continue
            if NEXT_RELATION in value.strip().strip('"').lower().split():
                return entry.group("url").strip() or None
    return None


def _split_outside_quotes(text: str, delimiter: str) -> list[str]:
    """Split `text` on `delimiter`, ignoring any that falls inside a quoted-string.

    A copy of `app.services.roster_sync::_split_outside_quotes`, whose docstring
    carries the argument: between the quotation marks of an RFC 9110 §5.6.4
    quoted-string every character is content, so a bare `str.split(";")` reads
    `title="a; rel=next"; rel="prev"` as three parameters and lets a platform choose
    which of its addresses this tool walks into out of a string it never offered as
    a relation. An unterminated quotation mark leaves the rest quoted, which is the
    reading that refuses to find a relation rather than inventing one.
    """
    parts: list[str] = []
    held: list[str] = []
    quoted = False
    escaped = False
    for character in text:
        held.append(character)
        if escaped:
            escaped = False
        elif quoted and character == "\\":
            escaped = True
        elif character == '"':
            quoted = not quoted
        elif character == delimiter and not quoted:
            held.pop()
            parts.append("".join(held))
            held = []
    parts.append("".join(held))
    return parts


# ---------------------------------------------------------------------------
# The call log.
# ---------------------------------------------------------------------------


def _answered_status(refusal: LtiServiceException) -> int | None:
    """The HTTP status behind one `LtiServiceException`, or `None` if it carries none.

    Defensive rather than `refusal.response.status_code`, because the attribute is
    the library's: a version that stopped setting it would otherwise turn a refusal
    this function exists to describe into an `AttributeError` inside the error path.
    """
    answered = getattr(getattr(refusal, "response", None), "status_code", None)
    return answered if isinstance(answered, int) else None


def _record_call(session: Session, section_id: UUID, url: str, response_code: int | None) -> None:
    """Write down one AGS HTTP call. Not LMS-owned, so no sanction is spent here.

    **One row per HTTP call**, which is SPEC §6.1's grain: posting one score is a
    token request and a post, and creating a column is a walk and a create before
    either, so a row per *post* could not tell an operator which of them failed.

    The row carries the URL, the status, the instant and the section, and nothing
    else — no score, no ledger line, no LMS user id (settled decision 5). A call
    log that grew a value column would be a per-student record of standing on a
    table SPEC §6.1 puts on an operator's console.

    Flushed rather than committed: the caller owns the transaction.
    """
    session.add(
        AgsCall(
            section_id=section_id,
            url=url,
            response_code=response_code,
            called_at=datetime.now(UTC),
        )
    )
    session.flush()
