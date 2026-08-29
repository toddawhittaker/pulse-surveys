"""The hourly NRPS roster pull, as a conformant LTI Advantage service client (E1-11).

SPEC §2.1 gives courses, sections and enrollments two arrival paths — "hourly
roster sync + launch-time ingestion" — and §7.3 gives this one its schedule and
its discovery rule: NRPS is "pulled on schedule and on launch (debounced)", and
the roster address a staff launch stored is the only way the scheduled half ever
learns a section exists. `app.services.provisioning` is the other path; this is
the one that fills a section in.

**The outbound transport is a parameter, and it has to be.** Every service call
here goes through `pylti1p3`'s `ServiceConnector`, which takes its transport as a
constructor argument (`ServiceConnector(registration, requests_session=…)`), and
this module passes whatever its caller handed it. That is a hard interface
requirement rather than a convenience: in a test neither the mock platform's
advertised address nor this tool's own resolves over a network, so a sync that
built its own `requests.Session` internally could not be driven against a platform
by any test at all — no token exchange to inspect, no `Authorization` header to
read, and the whole of E1-11's criterion 1 unassertable. In production nobody
passes one and a plain session is built here.

**What "conformant" means, and why it is not visible in a 200.** The carried
client-credentials entry defines it: a token requested with a tool-signed
assertion, attached to every service call. This mock's Advantage services
deliberately do not require a token (ADR 0084's consequences; E1-06 ruled that
enforcement pairs with a later ticket), so an unauthenticated GET of a roster
still answers 200 — which is exactly why there is no unauthenticated path in this
module to fall back to. Every read goes through the connector, so every read
carries the token or does not happen.

**Whose credentials.** The registration is resolved from the section's own
`lti_deployment_id` and from nothing else (deferred E1-10 item 1, ADR 0091). A
resolver that took whichever registration it found first would sign an assertion
audienced at one platform and present the resulting token to another
institution's roster service, and both halves of that are silent.

**What it writes, and through what.** `user`, `enrollment` and the teaching
instructor's `INSTRUCTOR` `role_assignment` are three of the four relations SPEC
§2.1 puts on the LMS's side, so every write here is preceded by `guard_write` with
this module's own catalog entry (ADR 0090; `SANCTIONED_WRITERS["roster_sync"]`).
The catalog does **not** grant `section`: §7.3 gives a section exactly one way to
be discovered, and it is not the roster of a section that must already exist for
the roster to be fetchable.

Two things it may not do directly, and the doors it uses instead (ADR 0094, and
this ticket's D7): it holds no read of `user.lms_user_id`, so a roster member is
matched to a `user` row through `public.resolve_platform_user`; and it holds no
privilege of any kind on `user_identity`, so an address is written through
`public.record_roster_email`. Both are `SECURITY DEFINER` functions owned by roles
that exist for nothing else.

**The window columns are the platform's and the date columns are Pulse's**, which
is the whole of ADR 0095 and the reason there are four of them. Nothing here ever
writes a value into `lms_window_start` or `lms_window_end` that the platform did
not send: SPEC §3.4 has a different denominator for a student the platform gave no
dates for, and a synthesized value is indistinguishable from a real one
afterwards.

**Nothing here commits.** The caller owns the transaction, exactly as
`provision_from_launch` leaves its writes to ride inside the launch's session;
`app.jobs.tasks` is where a commit happens for the scheduled and triggered runs.
"""

import logging
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any, Final
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID
from zoneinfo import ZoneInfo

import requests
from pylti1p3.exception import LtiServiceException
from pylti1p3.names_roles import NamesRolesProvisioningService
from pylti1p3.service_connector import ServiceConnector
from sqlalchemy import insert, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import Settings, canonical_host, url_host
from app.lti.launch import INSTRUCTOR_ROLE_URI, stated_roles
from app.lti.registration import NoSigningKeyError, OrmToolConf
from app.models.identity import AssignmentRole, Enrollment, User
from app.models.lti import (
    ROSTER_SERVICE_ADDRESS_COLUMN,
    LtiDeployment,
    LtiPlatform,
    NrpsCall,
    RegistrationAddressError,
    refuse_invalid_fetched_address,
)
from app.models.org import Section
from app.services.authz import (
    LmsOwnedWriteRefused,
    WriteSanction,
    guard_write,
    sanction_for,
    teaching_instructor_assigned,
)

__all__ = ["request_section_sync", "sync_all_rosters", "sync_section"]

logger = logging.getLogger("app.services.roster_sync")

# This module's name in `authz.SANCTIONED_WRITERS`, resolved once at import so a
# name the catalog does not hold fails when the process starts rather than on
# somebody's hourly run (ADR 0090).
SANCTION: Final[WriteSanction] = sanction_for("roster_sync")

# The scope NRPS 2.0 names for reading a context's membership. A specification
# constant: the token endpoint grants for the exact string the service claim
# carries, and one granted for anything else is a token the service refuses. It is
# the same string `NamesRolesProvisioningService` asks for on every page, so a token
# obtained under it here is the one the walk spends — `ServiceConnector` caches per
# scope set, which is what keeps a paged sync to one grant.
MEMBERSHIP_SCOPE: Final[str] = (
    "https://purl.imsglobal.org/spec/lti-nrps/scope/contextmembership.readonly"
)

# How many pages of one container this tool will follow before it gives up. **A
# bound on somebody else's header**, not a page budget: the `Link` relation a walk
# follows is composed by the platform, so a header that advertises a next page for
# ever is a worker that never finishes and an `nrps_call` table that never stops
# growing. A thousand is far past any real section — platforms page rosters at
# fifty or more, so a section would need tens of thousands of members to reach it —
# and a walk that hits it is reported as a refusal rather than truncated, for the
# reason `_walked_roster` gives.
MAX_PAGES_WALKED: Final[int] = 1000

# How long a launch trigger is debounced by a call this section has already made.
# **Five minutes** (E1-11's D9, recorded in ADR 0095): SPEC §7.3 debounces the
# launch trigger because a class of thirty opening the tool at the top of the hour
# would otherwise ask the platform for one roster thirty times.
DEBOUNCE_WINDOW: Final[timedelta] = timedelta(minutes=5)

# NRPS 2.0's three membership statuses. Two of them are a drop; a member document
# stating none is read as `Active`, which is what a container that omits the
# member means and what every real platform sends for somebody still enrolled.
MEMBER_STATUS = "status"
DROPPED_STATUSES: Final[frozenset[str]] = frozenset({"Inactive", "Deleted"})

# One `<url>` of an RFC 8288 `Link` header, with the parameter list belonging to
# it. The parameter tail stops at a comma so that two links in one header are read
# as two, which is the shape a platform sends when it offers `prev`, `next` and
# `first` together; `[^>]*` inside the angle brackets is the URI-reference, which
# RFC 8288 §3 says carries no `>` unencoded — and which is why a comma *inside* a
# link's URL cannot end it either.
#
# **A quoted parameter value is a single value, comma and semicolon included**
# (RFC 9110 §5.6.4, which RFC 8288 §3 builds its parameters on). That is the
# alternation in the tail: a run of characters that are neither delimiter nor
# quote, or a whole quoted-string with its `\"` escapes. A tail that stopped at
# the first comma read `<url>; title="Page 2, of 9"; rel="next"` as a link ending
# mid-title, whose `rel="next"` belonged to nothing — the walk ends early and
# **complete**, which is H1's own silent truncation reached through a spelling the
# specification explicitly permits.
#
# **This tool reads the header itself rather than taking `pylti1p3`'s answer**, and
# the boundary review's H1 is why. `ServiceConnector.make_service_request` searches
# a **lower-cased** copy of the whole header with `<([^>]*)>;\s*rel="next"`, and
# that is wrong twice over: RFC 3986 §6.2.2.1 makes a URL's path and query
# case-sensitive, so a platform paging on a base64 cursor (Canvas's
# `?page=Bookmark:QUJDeHl6`) is asked for a page it does not serve; and the pattern
# requires `rel` to be the link's *first* parameter and its value to be quoted,
# where RFC 8288 §3 makes a link's parameters unordered and its `rel` value a token
# that may be bare. A header the pattern misses ends the walk early **as complete**,
# which closes the enrollment of every member on the pages that were never fetched.
LINK_HEADER_ENTRY: Final[re.Pattern[str]] = re.compile(
    r"""<(?P<url>[^>]*)>                    # the URI-reference, opaque between the brackets
        (?P<parameters>                     # its parameters, up to the next link
            (?: \s*;                        # each one introduced by a semicolon
                (?: [^,;"] | "(?:[^"\\]|\\.)*" )*   # bare text, or a whole quoted-string
            )*
        )""",
    re.VERBOSE,
)

# The link relation a paged container advertises its next page under (RFC 8288 §3
# and NRPS 2.0 §3.2), and the name of the header carrying it.
NEXT_RELATION: Final[str] = "next"
LINK_HEADER: Final[str] = "link"

# The member document's own names for a subject, its roles and its address, as
# NRPS 2.0 spells them.
MEMBER_SUBJECT = "user_id"
MEMBER_ROLES = "roles"
MEMBER_EMAIL = "email"

# The two members of an enrollment-window extension object, as ADR 0048 fixes
# them: `start` is required on a member that carries the extension at all, and
# `end` is present and null for somebody still enrolled.
WINDOW_START = "start"
WINDOW_END = "end"

# What makes a member key an *extension* rather than one of the specification's
# own. ADR 0048 forbids naming the URI itself here — "Nothing in `backend/` may
# hardcode this URI. It is one platform's spelling of one vendor extension, and
# the tool's side of it is an adapter" — and E1-11's boundary does not build E3's
# adapters. So the extension is found by the two properties ADR 0048 fixes and no
# platform's spelling of them: a member key that is an absolute URI, whose value is
# an object carrying a `start`. See ADR 0095 for what this stands in for.
URI_MEMBER_MARK = "://"

# The one point-resolution call that turns a roster member into a `user` row, and
# the one that turns that row into a `person`. ADR 0094: this connection holds no
# read of `user.lms_user_id` and no privilege on `person`, so both are point
# queries through a definer function rather than a lookup.
_RESOLVE_PLATFORM_USER = text(
    "SELECT public.resolve_platform_user(CAST(:platform_id AS uuid), CAST(:subject AS text))"
)
_RESOLVE_PERSON_FOR_USER = text("SELECT public.resolve_person_for_user(CAST(:user_id AS uuid))")

# D7's writer. The whole of what this module may do to `user_identity`: an address
# where the platform exposed one, a null where it stopped, and never a name.
_RECORD_ROSTER_EMAIL = text(
    "SELECT public.record_roster_email(CAST(:user_id AS uuid), CAST(:email AS text))"
)

# F2's writer, and the reason this module holds no `INSERT` on `role_assignment`
# directly any more. A grant can bound a table and its columns; it cannot bound a
# column's *value*, so a table-wide `INSERT` let the application connection write a
# `CARE` row — the row E0-10's reveal definers check for — as readily as the
# `INSTRUCTOR` one `guard_write` was the only thing refusing. The definer's body
# writes `'INSTRUCTOR'` and its signature has nowhere to put another role, exactly
# as `record_roster_email` bounds the write to an address and never a name. ADR 0096
# records it.
_RECORD_TEACHING_INSTRUCTOR = text(
    "SELECT public.record_teaching_instructor(CAST(:person_id AS uuid), CAST(:section_id AS uuid))"
)


class RosterSyncError(RuntimeError):
    """This section's roster could not be reached at all, and no call was made.

    Raised rather than logged for the conditions that are true of the *deployment*
    rather than of one section — no registration behind the section's deployment,
    no tool signing key — because every section in the institution has the same
    problem and a run that swallowed it would leave an operator reading a product
    full of sections that look never-synced. A refusal or a failure *from* the
    platform is a different thing: it is one section's fact, it is recorded in
    `nrps_call` with its response code, and it does not raise.
    """


@dataclass(frozen=True)
class _Member:
    """One roster member, read into the values this module writes.

    `unreadable` is the per-member refusal E1-11's D4 asks for: a member whose
    extension carries a naive or unparseable timestamp gets **no enrollment row**,
    while the member beside it is ingested normally. The two ways round that are
    both forbidden — letting the value reach the column, where `AwareDateTime`
    raises (ADR 0019) and takes the whole roster's transaction with it, and storing
    an absence, which would claim the platform sent no dates when it sent one
    nothing could read.
    """

    subject: str
    teaches: bool
    dropped: bool
    email: str | None
    window_start: datetime | None
    window_end: datetime | None
    unreadable: bool


# ---------------------------------------------------------------------------
# The entry points.
# ---------------------------------------------------------------------------


def sync_section(
    session: Session,
    section_id: UUID,
    http: requests.Session | None = None,
    settings: Settings | None = None,
    resolve: Callable[[str], Sequence[str]] | None = None,
) -> None:
    """Pull one section's roster and write what it says. The whole of the sync.

    Both SPEC §7.3 paths converge here: `app.jobs.tasks.sync_section_roster` calls
    it for the one section a staff launch just touched, and `sync_all_rosters`
    calls it for each section that carries a stored address.

    **A section with no stored address is not called at all**, and that is a state
    rather than a silence: §7.3 makes it never-synced, "a state distinct from
    empty", and the discriminator is that it has no `nrps_call` rows either. A
    walk that attempted a sync with no URL would either die per section or write a
    failed call row, and the second makes the two states indistinguishable.

    `http` is the transport every outbound call travels over — see the module
    docstring for why it is a parameter. `settings` supplies the institution
    timezone the sync's own dates are stamped in (SPEC §3.1) and the environment the
    fetched-address rules are judged under (F1); both default to values built here,
    so a caller that has neither passes neither.

    **The environment reaches the address rules from `Settings`, never from
    `os.environ`.** That is the read deferred E1-10 item 5 removed from the writer
    next door, and F1 asks for the same discipline here: a URL the walk is about to
    fetch is judged by the same rules the stored address was, and those rules take
    the environment name.

    `resolve` is the resolution seam rule 5 needs (ADR 0101), handed on to the
    address rules and defaulted by them to a real name lookup. It is a parameter
    for the reason `http` is: no test in this repository may reach a name server,
    because a hostname resolves differently on a developer's machine and in CI —
    and a rule measured against a resolver is measuring the machine.

    **The connection goes to the address that was judged.** Each host the walk
    judges is pinned to the first address it resolved to, and
    `PinnedResolutionAdapter` below sends the GET there under the platform's own
    hostname. Judging a name and then letting the transport resolve it again is a
    check of one thing and a request to another — the same shape as a redirect,
    one layer down.
    """
    settings = Settings() if settings is None else settings
    section = session.get(Section, section_id)
    if section is None:
        raise RosterSyncError(
            f"there is no section {section_id} to sync. A task enqueued for a section that has "
            "since been deleted is a condition to see rather than a roster to fetch."
        )
    address = section.lms_context_memberships_url
    if address is None:
        logger.info(
            "section %s carries no stored roster address, so it is never-synced and no call was "
            "attempted (SPEC 7.3)",
            section_id,
        )
        return

    # One pin table per sync, shared by reference with the adapter that reads it:
    # the walk fills it in as it judges each host, and the next request out of the
    # transport is already pinned.
    pins: dict[str, str] = {}
    transport = _pinned(_no_redirects(http), pins)
    platform = _platform_for(session, section)
    connector = ServiceConnector(_registration_for(session, platform), requests_session=transport)
    walked = _walked_roster(
        session,
        section_id,
        address,
        connector,
        settings.environment,
        resolve=resolve,
        exempt_host=url_host(address),
        pins=pins,
    )
    if walked is None:
        return
    members, complete = walked
    _ingest(
        session,
        section,
        platform.id,
        _deduplicated(members, section_id),
        _today(settings),
        complete=complete,
    )


def _no_redirects(http: requests.Session | None) -> requests.Session:
    """The transport the sync fetches over, with redirect-following turned off (F1).

    A redirect is the same bypass as a hostile `Link` header arriving one step
    earlier: the address `refuse_invalid_fetched_address` judged is not the address
    the request ends at, so a client that follows a 30x has validated nothing. This
    tool follows none.

    `requests` has no session-level `allow_redirects`, and `pylti1p3`'s
    `ServiceConnector` calls `get`/`post` without the per-request flag — so the one
    lever that reaches its internal calls is `max_redirects`, and `0` makes any 30x
    raise `TooManyRedirects` (a `RequestException`, recorded as a refused call)
    rather than being followed. It is set on the session the caller handed in when
    there is one, so a test driving a redirect over its own wire is covered too, and
    on a fresh session in production where `http` is `None`.
    """
    session = requests.Session() if http is None else http
    session.max_redirects = 0
    return session


class PinnedResolutionAdapter(requests.adapters.BaseAdapter):
    """Send a request for a judged host to the address that was judged (ADR 0101).

    Rule 5 resolves a fetched URL's host and refuses every returned address that
    is not one this container may reach. Between that answer and the GET the name
    can be resolved again — by the transport, milliseconds later — and answer
    something else: the platform's own DNS serves a public address while the walk
    is judging and a private one while the page is being fetched, and every rule
    has been satisfied about an address the packet never went to. That is the
    redirect bypass one layer down, and this adapter is what closes it.

    **What it does to a pinned request**, and nothing else: the URL's host becomes
    the pinned address, and the `Host` header states the original hostname (with
    its explicit port, where the URL carried one) so the platform serves the right
    virtual host. **A host with no pin passes through untouched** — the token
    endpoint, a development stack's own exempt roster host, and the in-process
    transport a test hands in are all unpinned, and an adapter that rewrote a host
    it holds no pin for would send a request to an address nothing judged.

    **TLS is verified against the name, not the address.** A request addressed to
    an IP literal would otherwise have its certificate checked against the
    address, which no LMS's certificate names — a pin that dropped the name would
    turn every real deployment's sync into a TLS failure. urllib3 takes the name
    as `server_hostname` (SNI) and `assert_hostname` on the connection pool, and
    `requests` passes pool keywords through `HTTPAdapter.init_poolmanager`, so one
    pinned transport is built per hostname and kept. An inner adapter that is not
    a `requests` HTTP adapter opens no socket and has no TLS to arrange — that is
    the suite's in-process wire — and is delegated to as it is.

    It resolves nothing itself. The pins are the walk's, filled in by the address
    rules' own answer, so there is exactly one resolution per host per sync and
    the adapter cannot disagree with what was judged.
    """

    def __init__(self, inner: requests.adapters.BaseAdapter, pins: Mapping[str, str]) -> None:
        self.inner = inner
        self.pins = pins
        self._pinned_transports: dict[str, requests.adapters.HTTPAdapter] = {}

    def send(
        self,
        request: requests.PreparedRequest,
        stream: bool = False,
        timeout: float | tuple[float | None, float | None] | None = None,
        verify: bool | str = True,
        cert: str | tuple[str, str] | None = None,
        proxies: dict[str, str] | None = None,
    ) -> requests.Response:
        split = urlsplit(str(request.url))
        # The same helper the pin was written under, and that is the whole of the
        # correctness here: a host has more than one legal spelling, and a lookup
        # that folded it differently would miss its own pin and hand the request
        # to a transport that resolves the name a second time. The URL is the one
        # `requests` prepared, so its host is already lower-cased and IDNA-encoded
        # and may still carry a trailing dot; `canonical_host` answers for that
        # spelling and for the one the `Link` header carried alike.
        hostname = canonical_host(split.hostname) or ""
        address = self.pins.get(hostname)
        sending = self.inner if address is None else self._transport_for(split.scheme, hostname)
        if address is not None:
            # The authority exactly as `requests` prepared it — the trailing dot
            # and the encoded form included — so the platform is asked for the
            # virtual host an unpinned request would have asked it for, byte for
            # byte, and its certificate is checked against the name it serves
            # rather than against a spelling this tool tidied up.
            authority = split.netloc.split("@")[-1]
            request.url = urlunsplit(
                (
                    split.scheme,
                    _netloc_at(address, split.port),
                    split.path,
                    split.query,
                    split.fragment,
                )
            )
            request.headers["Host"] = authority
        return sending.send(
            request, stream=stream, timeout=timeout, verify=verify, cert=cert, proxies=proxies
        )

    def _transport_for(self, scheme: str, hostname: str) -> requests.adapters.BaseAdapter:
        """The transport a pinned request travels over — see the class docstring."""
        if scheme != "https" or not isinstance(self.inner, requests.adapters.HTTPAdapter):
            return self.inner
        held = self._pinned_transports.get(hostname)
        if held is None:
            held = requests.adapters.HTTPAdapter()
            held.init_poolmanager(
                requests.adapters.DEFAULT_POOLSIZE,
                requests.adapters.DEFAULT_POOLSIZE,
                server_hostname=hostname,
                assert_hostname=hostname,
            )
            self._pinned_transports[hostname] = held
        return held

    def close(self) -> None:
        for held in self._pinned_transports.values():
            held.close()
        self.inner.close()


def _netloc_at(address: str, port: int | None) -> str:
    """One resolved address as a URL authority, bracketed where IPv6 needs it."""
    host = f"[{address}]" if ":" in address else address
    return host if port is None else f"{host}:{port}"


def _pinned(http: requests.Session, pins: Mapping[str, str]) -> requests.Session:
    """Mount `PinnedResolutionAdapter` over whatever this session already answers with.

    Both schemes, because a walk that judged an `http` page must reach the address
    it judged too. The adapter it wraps is the one the session holds, which in a
    test is the in-process wire and in production is `requests`' own — so a caller
    that handed in a transport keeps it.

    A session already carrying one of these is re-wrapped around its *inner*
    adapter rather than around the whole thing: `sync_all_rosters` hands the same
    session to every section in the institution, and a wrapper per section would
    be a chain hundreds deep by the end of an hourly run, each link holding a pin
    table belonging to a section already synced.
    """
    for scheme in ("https://", "http://"):
        held = http.get_adapter(scheme)
        inner = held.inner if isinstance(held, PinnedResolutionAdapter) else held
        http.mount(scheme, PinnedResolutionAdapter(inner, pins))
    return http


def sync_all_rosters(
    session: Session,
    http: requests.Session | None = None,
    settings: Settings | None = None,
) -> None:
    """Sync every section that carries a stored roster address. The hourly job's body.

    SPEC §7.3 gives the scheduled half exactly one discovery rule — the address a
    staff launch stored — so the query below is the whole of what the hour knows
    about which sections exist.

    **The connector is built per section, inside `sync_section`**, and that is not
    an accident of structure: one built before this loop would present the first
    platform's credentials to every section in the institution, which is deferred
    E1-10 item 1's failure arriving one level up from where that item found it.

    **One section's failure — of any kind — does not end the hour** (F3). The catch
    is broad on purpose: the sync raises the errors it was written to raise, and what
    silences a walk is the one it was not — a token body carrying no `access_token`
    makes `pylti1p3` raise `KeyError`, a roster answering a bare list makes it raise
    `AttributeError`, and either from one platform escaping a narrower `except` ends
    the hour for every section after it, with nothing on §6.1's console for the ones
    never reached. So each section runs inside a savepoint: its own partial work is
    rolled back on a failure and the sections before it are not, the failure is
    recorded against the section it belongs to as a call this tool could not
    complete, and the walk moves on. A broad `except` here is defended by that
    boundary — it cannot swallow a bug into a green run, because a failed section
    still leaves a red mark an operator reads.
    """
    addressed = list(
        session.scalars(select(Section.id).where(Section.lms_context_memberships_url.is_not(None)))
    )
    logger.info(
        "the scheduled roster walk found %d section(s) with a stored address", len(addressed)
    )
    for section_id in addressed:
        savepoint = session.begin_nested()
        try:
            sync_section(session, section_id, http=http, settings=settings)
            savepoint.commit()
        except Exception:
            savepoint.rollback()
            logger.exception("the scheduled roster walk could not sync section %s", section_id)
            _record_section_failure(session, section_id)


def _record_section_failure(session: Session, section_id: UUID) -> None:
    """Leave a call row for a section whose scheduled sync failed unexpectedly (F3).

    Against the section's own stored address, `response_code` NULL: §6.1's console
    then shows a section whose platform answered something this tool could not read,
    rather than a section that was never attempted — which is what a walk that
    continued but recorded nothing would leave. Written *after* the section's own
    savepoint was rolled back, so a failure that left the session mid-statement
    cannot take this row with it; and itself guarded, because the one thing this
    must not do is turn one section's failure back into the whole walk's.
    """
    try:
        section = session.get(Section, section_id)
        address = section.lms_context_memberships_url if section is not None else None
        _record_call(session, section_id, address or "", None, None)
    except Exception:
        logger.exception(
            "section %s failed and its failure could not be recorded either", section_id
        )


def request_section_sync(session: Session, section_id: UUID) -> bool:
    """Ask for this section to be synced, unless it was synced a moment ago.

    SPEC §7.3's launch trigger, debounced. `app.api.lti.launch` calls it after a
    staff launch has been committed; the answer says whether a sync was enqueued,
    which is what a caller would log.

    **The window is measured against this section's own most recent call** and
    against nothing else. A debounce that read the newest `nrps_call` row in the
    table would silence every launch trigger in the institution for five minutes
    after any section synced — which, on an hourly schedule across a few hundred
    sections, is every launch trigger there is.

    **A section nobody has ever called is enqueued.** "Skip if there is any call
    row at all" passes a debounce test and turns every section into one that syncs
    exactly once.

    **A broker this call cannot reach must never fail the launch that made it.**
    This runs on a request, after the launch has already committed and after the
    person has already been authenticated, and what it is asking for is a
    *background* job whose absence costs at most an hour — `sync_rosters` visits
    every addressed section on the hour whatever happens here. So the publish is
    made with `retry=False`, so a Redis that is down fails at once rather than
    holding the request open through kombu's retry policy; with
    `ignore_result=True`, so nothing reaches the result backend, which has a retry
    policy of its own and is not consulted for a task whose answer nobody reads;
    and inside a `try`, because the one thing that must not happen is a person
    being unable to enter the product because a queue was unavailable. The failure
    is logged at error level, which is the visibility (`docs/MISTAKES.md` entry
    26), and the caller is told `False`.
    """
    since = datetime.now(UTC) - DEBOUNCE_WINDOW
    recent = session.scalars(
        select(NrpsCall.id)
        .where(NrpsCall.section_id == section_id, NrpsCall.called_at >= since)
        .limit(1)
    ).first()
    if recent is not None:
        logger.info(
            "section %s was called within the last %d seconds, so this launch trigger is "
            "debounced (SPEC 7.3)",
            section_id,
            int(DEBOUNCE_WINDOW.total_seconds()),
        )
        return False

    # Imported here rather than at module scope because `app.jobs.tasks` imports
    # this module: the task is a thin wrapper over these functions (D10), so a
    # top-level import would be a cycle.
    from app.jobs.tasks import sync_section_roster

    try:
        sync_section_roster.apply_async(args=[str(section_id)], retry=False, ignore_result=True)
    # Broad on purpose, and the docstring is the argument: kombu, redis-py and
    # Celery each raise their own family here, and an enumerated list of them is a
    # list that goes stale into a launch failure.
    except Exception:
        logger.exception(
            "section %s could not be enqueued for a roster sync; the hourly walk will reach it",
            section_id,
        )
        return False
    return True


# ---------------------------------------------------------------------------
# Whose credentials, and the walk they pay for.
# ---------------------------------------------------------------------------


def _platform_for(session: Session, section: Section) -> LtiPlatform:
    """The registration this section was discovered through, and the only one.

    `section.lti_deployment_id → lti_deployment → lti_platform`, and nothing else.
    That chain is the section's own identity (ADR 0091): a context identifier is
    unique inside one registration and meaningless across registrations, so the
    registration that discovered a section is the only one whose credentials mean
    anything at its roster address, and the only one whose subject keys mean
    anything in its roster. Deferred E1-10 item 1 is about both halves.

    Read once per section and handed to everything below it, so that "whose
    platform is this" is answered in one place per sync rather than per member.
    """
    platform = session.scalars(
        select(LtiPlatform)
        .join(LtiDeployment, LtiDeployment.lti_platform_id == LtiPlatform.id)
        .where(LtiDeployment.id == section.lti_deployment_id)
    ).one_or_none()
    if platform is None:
        raise RosterSyncError(
            f"section {section.id} is bound to deployment {section.lti_deployment_id}, which "
            "resolves to no registered platform. A section is bound to the registration it was "
            "discovered through, and without one there are no credentials to call its roster with."
        )
    return platform


def _registration_for(session: Session, platform: LtiPlatform) -> Any:
    """The `pylti1p3` registration for one platform row, ready to sign with.

    Built through `OrmToolConf`, which is the one construction path this tool has
    for a registration — E1-11 taught it to fill in the tool's private key and
    `kid` as well, so the inbound door and this outbound client read the same row
    of `tool_signing_key` and a platform verifying either sees the same key.

    The two refusals are loud because they are facts about the *deployment* rather
    than about one section: a registration with no token endpoint and a tool with
    no signing key both mean nothing can be synced anywhere, and a sync that
    swallowed either would leave an operator reading a product full of sections
    that look never-synced.
    """
    registration = OrmToolConf(session).find_registration_by_params(
        platform.issuer, platform.client_id
    )
    if registration is None or registration.get_auth_token_url() is None:
        raise RosterSyncError(
            f"the registration for issuer {platform.issuer!r} states no token endpoint, so no "
            "access token can be requested and no service call can be made. E1-05 adds "
            "`auth_token_url` to `lti_platform`; a registration written before it states none."
        )
    if registration.get_tool_private_key() is None:
        raise NoSigningKeyError(
            "This deployment holds no `tool_signing_key` row, so there is nothing to sign a "
            "`client_assertion` with and no platform will issue this tool a token. ADR 0082 "
            "records that a real deployment needs a supply route before it needs anything else."
        )
    return registration


def _walked_roster(
    session: Session,
    section_id: UUID,
    address: str,
    connector: ServiceConnector,
    environment: str,
    *,
    resolve: Callable[[str], Sequence[str]] | None,
    exempt_host: str | None,
    pins: dict[str, str],
) -> tuple[list[Mapping[str, Any]], bool] | None:
    """Every member of the container at `address`, following `rel="next"` to the end.

    Answers `(members, complete)` — the members read, and whether the walk reached a
    page that advertised no next relation — or `None` when there is no usable roster
    at all. `complete` is what `_ingest` reads to decide whether it may close the
    enrollment of a member the container did not carry: a member missing from a
    *complete* walk has left, and a member missing from a *truncated* one is on a
    page this tool never fetched.

    **One `nrps_call` row per HTTP call**, which is D9's grain and is load-bearing
    three times over: it is SPEC §6.1's "NRPS and AGS call logs with response
    codes", it is the never-synced discriminator, and it is the debounce's memory.
    A row per *sync* would leave an operator unable to tell a roster that took four
    requests from one that took one.

    **Every URL the walk is about to fetch is judged first (F1).** The stored first
    page and every `rel="next"` the platform names pass
    `refuse_invalid_fetched_address` before the GET — link-local by rule 4, loopback
    by the roster column's own rule, cleartext-off-this-machine by rule 1 — because
    the walk adopts an address the *platform* chose at run time, and a compromised
    one points it at the cloud metadata service or a loopback listener with the
    tool's Bearer token attached. A URL that fails is a refusal recorded **against
    the section's stored address, not the hostile one** (a hostile URL written into
    the log a console reads back is a second channel), `response_code` NULL, the
    refused URL in the log line only. The walk stops there and keeps what earlier,
    validly-fetched pages already read — so a class that synced correctly up to a
    hostile second page is not thrown away. ADR 0096 records it.

    **The judgment resolves the host, and its answer is what the connection is
    made to** (ADR 0101). Rule 5 refuses a page whose host resolves to an address
    this container may not reach — the residual finding E1-11 recorded, an
    internal service holding a valid certificate on a private address, which every
    rule that reads a spelling passes. The first address a host resolves to is
    written into `pins`, and `PinnedResolutionAdapter` sends the GET there under
    the platform's own hostname; a host already pinned is judged again on a later
    page and never re-pinned, so a name that starts answering a private address
    stops the walk while a name that merely answers a different public address
    cannot move the connection. In development the section's own stored host is
    exempt and is not resolved at all — `exempt_host` is that address's host —
    because it is the operator's own and the hourly walk would otherwise pay a
    lookup per page of every section.

    **A token failure answers `None`**, because it leaves no usable prefix: the
    token endpoint refused everything, no page was ever asked for, and `_ingest`
    never runs. The call is recorded, with the response code that says which failure
    it was; a NULL response code means the call never reached the platform at all.

    **A page that could not be fetched answers what was already read, incomplete** —
    the same answer a refused address gets, for the same reason (the boundary
    review's H1 pair). A page-boundary failure that threw the container away would
    lose a class that synced correctly up to it, every hour, invisibly: the members
    of page one are on the roster whatever page two answered. `complete` is `False`,
    so nothing is closed on the strength of a walk that did not reach the end.

    **The next page is read out of the response's own `Link` header** by
    `_next_page_url`, rather than from the `next_page_url` `pylti1p3` computes. See
    `LINK_HEADER_ENTRY` for what that library gets wrong and why the walk cannot use
    it. `get_nrps_data` is the same call `get_members_page` makes — same scope, same
    `Accept` — and it is used here because it hands back the headers as well.

    **A refused token is recorded against the roster's own URL, carrying the token
    endpoint's status.** A sync makes two calls to two endpoints and only one of
    them is the roster: when the *token endpoint* answers an error the roster is
    never asked at all. The URL is still the roster's, because the row is this
    section's record of an attempted sync and §6.1's console reads it per section.
    The status is the token endpoint's, because a NULL there has exactly one meaning
    under D9 — the call never reached the platform — and the two failures an
    operator has to tell apart are precisely "this deployment's credentials were
    refused, and the platform is up" and "nothing answered". Only the status
    separates them.

    **The eager fetch below is redundant and is kept deliberately.** An earlier
    version of this docstring claimed a walk left to discover the refusal on its
    first page "writes no row"; that is false of the code underneath it. The page
    handler further down catches the same `LtiServiceException` and records the same
    status against the URL it called — and `ServiceConnector` caches a token per
    scope set per connector with no expiry check, so exactly one grant is attempted
    per sync and it is attempted on the first page, whose URL is this section's
    stored address. Measured: removing the eager fetch leaves all fourteen tests of
    the conformance and debounce modules green.

    What it buys is that the recorded URL is the stored address because this
    function says so, rather than because of where the library's cache happens to
    put the only grant — which stops being true if that cache ever honours
    `expires_in` or a connector is reused across sections. ADR 0095 records the
    measurement and says a later reader may delete this after repeating it.
    """
    try:
        connector.get_access_token([MEMBERSHIP_SCOPE])
    except LtiServiceException as refusal:
        answered = _answered_status(refusal)
        _record_call(session, section_id, address, answered, None)
        logger.warning(
            "the token endpoint answered %s for section %s, so no call was made to its roster at "
            "%s: this deployment's credentials were refused rather than its roster service",
            answered,
            section_id,
            address,
        )
        return None
    except requests.RequestException:
        _record_call(session, section_id, address, None, None)
        logger.exception(
            "no access token could be obtained for section %s, so no call was made to its roster "
            "at %s",
            section_id,
            address,
        )
        return None

    service = NamesRolesProvisioningService(connector, {"context_memberships_url": address})
    members: list[Mapping[str, Any]] = []
    walked: set[str] = set()
    following: str | None = address
    while following is not None:
        if following in walked or len(walked) >= MAX_PAGES_WALKED:
            logger.error(
                "the roster walk for section %s reached %s after %d page(s) and stopped: a `Link` "
                "header that returns to a page it already served, or one that never says stop, is "
                "a container this tool cannot read to the end",
                section_id,
                following,
                len(walked),
            )
            return None
        try:
            resolved = refuse_invalid_fetched_address(
                environment,
                column=ROSTER_SERVICE_ADDRESS_COLUMN,
                address=following,
                resolve=resolve,
                development_exempt_host=exempt_host,
            )
        except RegistrationAddressError as refusal:
            # Against the section's stored address, never the hostile one: a URL the
            # platform chose, written into a record a console reads back, is a second
            # channel the review named. The refused URL is in the log line only.
            _record_call(session, section_id, address, None, None)
            logger.warning(
                "section %s was told to fetch a roster page at %s, which this container refuses: "
                "%s. The walk stopped and kept the %d member(s) already read.",
                section_id,
                following,
                refusal,
                len(members),
            )
            return members, False
        # The first resolution of a host is the one the connection is made to, and
        # a later one never moves it. A page judged again mid-walk is judged again
        # — a name that has started answering a private address stops the walk —
        # but the address the transport dials was fixed the first time this host
        # passed, which is the whole of the pin.
        judged_host = url_host(following)
        if resolved and judged_host is not None and judged_host not in pins:
            pins[judged_host] = resolved[0]
        walked.add(following)
        called = following
        try:
            answered_page = service.get_nrps_data(members_url=called)
        except LtiServiceException as refusal:
            answered = _answered_status(refusal)
            _record_call(session, section_id, called, answered, None)
            logger.warning(
                "the roster at %s answered %s, so section %s was not ingested past the %d member(s) "
                "already read",
                called,
                answered,
                section_id,
                len(members),
            )
            return members, False
        except requests.RequestException:
            _record_call(session, section_id, called, None, None)
            logger.exception(
                "the roster at %s could not be reached for section %s, which keeps the %d member(s) "
                "already read and closes nobody",
                called,
                section_id,
                len(members),
            )
            return members, False
        page = _page_members(answered_page)
        following = _next_page_url(answered_page["headers"])
        _record_call(session, section_id, called, 200, len(page))
        members.extend(page)
    return members, True


def _page_members(answered: Mapping[str, Any]) -> Sequence[Mapping[str, Any]]:
    """One page's members, read exactly as `NamesRolesProvisioningService` reads them.

    Deliberately no more forgiving than the library's own
    `data_body.get("members", [])`: a container that is not an object at all raises
    here, and that is the right answer rather than a shape to absorb. An unreadable
    body read as *no members* is an empty page, an empty page on a walk that then
    ends completely is a container this tool believes it read to the end, and
    `_ingest` closes the enrollment of everybody a complete walk did not carry. A
    loud failure is one section's, caught by `sync_all_rosters`' savepoint and
    recorded against that section; a quiet empty page ends a whole class's term.
    """
    body: Any = answered["body"]
    carried: Any = body.get("members", [])
    return list(carried)


def _next_page_url(headers: Mapping[str, Any]) -> str | None:
    """The next page a container's `Link` header advertises, spelled as it was sent.

    The boundary review's H1, and `LINK_HEADER_ENTRY` above carries the argument for
    reading the header here rather than taking `pylti1p3`'s answer for it. Three
    rules, all of them RFC 8288 §3's:

      - the header's parameters are **unordered**, so `rel` is looked for among all
        of them rather than required to be the first;
      - a `rel` value is a **token**, quoted or bare, and may name several relations
        on one link (`rel="first next"`), so the value is unquoted and split;
      - a header may carry **several comma-separated links**, so each is read and
        only the one declaring `next` is followed;
      - a **quoted** parameter value is one value whatever it contains, so a
        parameter is separated from the next by a semicolon *outside* quotation
        marks. A `rel=next` written inside some other parameter's quoted value is
        that value's text and not a relation this platform declared — and the
        difference decides where the tool sends its access token, so it is the
        platform's declaration that governs and never a string it quoted.

    The header's name is matched case-insensitively, because RFC 9110 §5.1 makes a
    field name case-insensitive and RFC 8288 §3 spells this one `Link`, which is
    what a real platform sends.

    The URL is handed back byte for byte. Nothing is lower-cased, unescaped or
    resolved against the page it came from: what a platform put between the angle
    brackets is what it will answer to, and a relative reference — which no platform
    in this system sends — is left to `refuse_invalid_fetched_address` to refuse
    rather than guessed at here.

    The first `next` declared wins, which is how a client reads a header that
    repeats one, and it is what keeps a decoy link later in the header from moving
    the walk.
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

    RFC 9110 §5.6.4's quoted-string, which is what a `Link` header's parameter
    values are: between the quotation marks every character is content, including
    the `;` that separates two parameters, and `\\` escapes the character after it
    so that a quoted value can contain a quotation mark of its own.

    A bare `str.split(";")` reads `title="a; rel=next"; rel="prev"` as three
    parameters, two of them fragments of one title — and the fragment `rel=next`
    then answers the question "what relation does this link declare?" with a value
    the platform put inside quotation marks rather than with the relation it
    declared. That is the platform choosing which of its addresses this tool walks
    into, and how often, from a string it never offered as a relation.

    An unterminated quotation mark leaves the rest of the text quoted, so the
    delimiters inside it are content. That is the reading that refuses to find a
    relation rather than the one that invents one out of a malformed header.
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


def _deduplicated(roster: Sequence[Mapping[str, Any]], section_id: UUID) -> list[Mapping[str, Any]]:
    """The assembled pages with each subject kept once — its first occurrence (M2).

    A container is paged over a collection that is still changing: a member added,
    removed or re-ordered between the fetch of page one and the fetch of page two
    shifts every later row along, and the member on the boundary is served on both.
    Nothing about that is a defect at the platform. Before this, the second copy was
    written as a second enrollment for one user and one section, ADR 0023's
    exclusion constraint refused the overlap, and the uncaught `ExclusionViolation`
    took the section's whole sync with it — every hour, for as long as the platform
    kept paging that way.

    **Here rather than inside the ingest loop**, and by `user_id` rather than by
    anything coarser. A duplicate caught by catching the constraint violation would
    make a database constraint part of the ingest loop's control flow and leave the
    section half-written; a rule keyed on the page, or on the member's position,
    drops half of every class that pages. So the roster is one list of documents by
    the time `_ingest` sees it, and the constraint stays what it is — the guard over
    a *genuine* overlap, which this cannot produce and must not be allowed to hide.

    **First occurrence wins** because the walk reads a container in the platform's
    own order and the earlier page is the one this tool asked for first; there is no
    rule that would let it prefer the later copy, and inventing one would be this
    module deciding which of two identical documents is the truer.

    A member document with no usable `user_id` is passed through untouched: it is
    not a duplicate of anything, and `_read_member` is where a document that cannot
    be keyed is refused, with one refusal per member rather than a silent merge here.

    **The note carries a count and the section, and never a member.** That a
    platform re-serves members across its page boundary is a fact about the
    platform, and it is worth an operator's attention precisely because dedup makes
    it otherwise invisible; which student it was is no part of it, and SPEC §10
    keeps a roster's subjects and addresses out of the log.
    """
    kept: list[Mapping[str, Any]] = []
    seen: set[str] = set()
    repeated = 0
    for member in roster:
        subject = member.get(MEMBER_SUBJECT)
        if not isinstance(subject, str) or not subject:
            kept.append(member)
            continue
        if subject in seen:
            repeated += 1
            continue
        seen.add(subject)
        kept.append(member)
    if repeated:
        logger.info(
            "the platform served %d duplicate member document(s) across the pages of section %s's "
            "container, so the first occurrence of each was kept and the rest dropped; a container "
            "paged over a collection that is changing re-serves the member on the boundary",
            repeated,
            section_id,
        )
    return kept


def _answered_status(refusal: LtiServiceException) -> int | None:
    """The HTTP status behind one `LtiServiceException`, or `None` if it carries none.

    Both places a service call can be refused read the status the same way, through
    here rather than through a second copy of the same `getattr` chain
    (`docs/MISTAKES.md` entry 13): the token endpoint's refusal and the roster's are
    written into the same column of the same table, and D9 gives that column's NULL
    exactly one meaning — the call never reached the platform. A second reading that
    drifted would put one of the two failures under the other's meaning, which is
    the whole distinction §6.1's console is read for.

    Defensive rather than `refusal.response.status_code` because the attribute is
    the library's: `LtiServiceException` sets `.response` today and a version that
    stopped would otherwise turn a refusal this function is meant to describe into
    an `AttributeError` inside the error path.
    """
    answered = getattr(getattr(refusal, "response", None), "status_code", None)
    return answered if isinstance(answered, int) else None


def _record_call(
    session: Session,
    section_id: UUID,
    url: str,
    response_code: int | None,
    members_seen: int | None,
) -> None:
    """Write down one NRPS HTTP call. Not LMS-owned, so no sanction is spent here."""
    session.add(
        NrpsCall(
            section_id=section_id,
            url=url,
            response_code=response_code,
            members_seen=members_seen,
            called_at=datetime.now(UTC),
        )
    )
    session.flush()


# ---------------------------------------------------------------------------
# Reading a member document.
# ---------------------------------------------------------------------------


def _stated_window(member: Mapping[str, Any]) -> Mapping[str, Any] | None:
    """The enrollment-window extension this member carries, if it carries one.

    Found by the two properties ADR 0048 fixes rather than by any platform's
    spelling of the namespace, because that record forbids `backend/` naming the
    URI: the extension rides on a member key that is an absolute URI, and its value
    is an object carrying `start`. Both halves matter — a key test alone would pick
    up any vendor extension, and a `start` test alone is the "scan the member for
    anything that parses as a date" that ADR 0048's own context section rejects.

    More than one such member is not guessed between: the tool has no rule for
    choosing, and choosing would be this module inventing one. ADR 0095 records
    that this stands in for §7.3's `PlatformProfile` adapter, which is E3's.
    """
    carried = [
        value
        for name, value in member.items()
        if isinstance(name, str)
        and URI_MEMBER_MARK in name
        and isinstance(value, Mapping)
        and WINDOW_START in value
    ]
    if len(carried) > 1:
        logger.warning(
            "a roster member carries %d namespaced enrollment extensions and this tool has no rule "
            "for choosing between them, so it is read as carrying none",
            len(carried),
        )
        return None
    return carried[0] if carried else None


def _instant(value: Any) -> datetime | None | str:
    """One extension timestamp as an aware `datetime`, `None`, or a refusal.

    Three answers because there are three cases and two of them are routinely
    confused. `None` is the platform saying nothing, which ADR 0048 makes an
    explicit `null` on `end` and an absent extension on `start`. A `str` answer is
    the refusal: a value that does not parse, or one that parses and carries no
    offset — which ADR 0048 forbids in as many words ("an RFC 3339 timestamp
    carrying an offset, never a bare date") and which `AwareDateTime` refuses at
    the bind boundary anyway (ADR 0019), one member's bad value taking the whole
    roster's transaction with it.
    """
    if value is None:
        return None
    if not isinstance(value, str):
        return f"{value!r} is not a timestamp"
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return f"{value!r} is not an RFC 3339 timestamp"
    if parsed.utcoffset() is None:
        return f"{value!r} carries no UTC offset"
    return parsed


def _read_member(member: Mapping[str, Any]) -> _Member | None:
    """One NRPS member as the values this module writes, or `None` for an unusable one.

    `None` is a member with no `user_id`, which is a document this tool cannot key
    anything to — SPEC §4 keys every response to that value. An unreadable *window*
    is a different thing and stays a member: see `_Member.unreadable`.
    """
    subject = member.get(MEMBER_SUBJECT)
    if not isinstance(subject, str) or not subject:
        logger.warning("a roster member states no subject and cannot be ingested")
        return None

    status = member.get(MEMBER_STATUS)
    email = member.get(MEMBER_EMAIL)
    window = _stated_window(member)
    start = _instant(window.get(WINDOW_START)) if window is not None else None
    end = _instant(window.get(WINDOW_END)) if window is not None else None
    unreadable = [value for value in (start, end) if isinstance(value, str)]
    if unreadable:
        logger.warning(
            "the enrollment window a roster member carries cannot be read (%s), so that member is "
            "refused and the rest of the roster is ingested",
            "; ".join(unreadable),
        )

    return _Member(
        subject=subject,
        teaches=INSTRUCTOR_ROLE_URI in stated_roles(member.get(MEMBER_ROLES)),
        dropped=isinstance(status, str) and status in DROPPED_STATUSES,
        email=email if isinstance(email, str) and email else None,
        window_start=start if isinstance(start, datetime) else None,
        window_end=end if isinstance(end, datetime) else None,
        unreadable=bool(unreadable),
    )


# ---------------------------------------------------------------------------
# What the roster means for the rows.
# ---------------------------------------------------------------------------


def _today(settings: Settings | None) -> date:
    """The day this sync is running, in the institution's own calendar.

    SPEC §3.1 makes every moment in this product a moment in the institution
    timezone, and §8 makes that "a deployment-level setting". `started_on` and the
    fallback `ended_on` are Pulse's record of which *day* a member was first and
    last seen, so reading the server's clock instead is the defect deferred E1-10
    item 2 records against the launch path, written into a second module.
    """
    configured = Settings() if settings is None else settings
    return datetime.now(ZoneInfo(configured.institution_timezone)).date()


def _ingest(
    session: Session,
    section: Section,
    platform_id: UUID,
    roster: Sequence[Mapping[str, Any]],
    today: date,
    *,
    complete: bool,
) -> None:
    """Write one container's members into `user`, `enrollment` and `user_identity`.

    The order is the rule. Every member is resolved to a `user` row first, because
    everything below is keyed to one; then the roster's own members are written;
    then the enrollments this section holds for people the container did **not**
    carry are closed. Doing the last of those first would close a member's window
    and reopen it in the same transaction.

    **The close-the-vanished pass runs only when the walk was complete** (F1). A
    member absent from a container this tool read to its last page has left, and
    ending their enrollment is right; a member absent from a walk that stopped on a
    refused page is on a page this tool never fetched, and closing them would end a
    student's enrollment because a *later* page was hostile. So a truncated walk
    writes what it read and closes nobody.
    """
    read = [_read_member(member) for member in roster]
    members = [member for member in read if member is not None]

    resolved: dict[str, UUID] = {}
    for member in members:
        found = _resolve_member(session, platform_id, member)
        if found is not None:
            resolved[member.subject] = found

    open_rows = _open_enrollments(session, section.id)
    for member in members:
        if member.unreadable:
            continue
        user_id = resolved.get(member.subject)
        if user_id is None:
            continue
        _record_email(session, user_id, member.email)
        _record_enrollment(session, section, member, user_id, open_rows.get(user_id), today)
        if member.teaches:
            _record_the_teaching_instructor(session, section, user_id)

    if not complete:
        return
    present = set(resolved.values())
    for user_id, row in open_rows.items():
        if user_id not in present:
            _close(session, row, ended_on=today, window_end=None)


def _resolve_member(session: Session, platform_id: UUID, member: _Member) -> UUID | None:
    """This member's `user` row, written first if the deployment has never seen them.

    D6: the match is `(lti_platform_id, lms_user_id)` through
    `public.resolve_platform_user`, because E1-10's round-3 review revoked this
    connection's read of `lms_user_id` — a connection able to read it "can enumerate
    every subject that ever launched and join a response back to the person who
    gave it". Matching and enumerating are different privileges and this module only
    holds the first.

    **A member with an unreadable window is resolved and not written**, which is
    what keeps D4's refusal per-member in both directions: they are still on the
    roster, so the close-the-vanished pass below must not treat them as gone.

    The insert is insert-if-absent and the unique constraint decides, exactly as
    `app.services.provisioning` writes the launching subject's row: the row is never
    revised, so a lookup before it would answer a question the constraint already
    answers atomically.
    """
    found = _resolved_user(session, platform_id, member.subject)
    if found is not None or member.unreadable:
        return found

    try:
        guard_write(table="user", sanction=SANCTION)
    except LmsOwnedWriteRefused:
        logger.exception("the chokepoint refused the roster sync its write to `user`")
        return None

    savepoint = session.begin_nested()
    try:
        session.add(User(lti_platform_id=platform_id, lms_user_id=member.subject))
        session.flush()
        savepoint.commit()
    except IntegrityError:
        # A row another process wrote between the resolution above and this insert.
        # `UNIQUE (lti_platform_id, lms_user_id)` is what says so, and resolving
        # again is the answer rather than a retry loop. Narrow on purpose: anything
        # else that fails this insert is a defect to see, and the savepoint is what
        # lets it out of here without a half-written transaction behind it.
        savepoint.rollback()
    return _resolved_user(session, platform_id, member.subject)


def _resolved_user(session: Session, platform_id: UUID, subject: str) -> UUID | None:
    """ADR 0094's point query: this subject on this registration, or nothing."""
    found: UUID | None = session.execute(
        _RESOLVE_PLATFORM_USER, {"platform_id": platform_id, "subject": subject}
    ).scalar_one()
    return found


def _record_email(session: Session, user_id: UUID, email: str | None) -> None:
    """Store the address the platform exposed, or clear the one it stopped exposing.

    D7, through the one door this connection has. A member exposing no address
    gets no identity row created — absence is the honest state, and a row per
    member carrying a null address turns "this deployment holds an address for
    nobody" into "it holds a record for everybody, empty". A member whose address
    disappears has the field nulled: a platform that stops exposing addresses is a
    deployment that has withdrawn them. The function never writes a name (ADR
    0050), and its owner holds no privilege on the name column at all.
    """
    session.execute(_RECORD_ROSTER_EMAIL, {"user_id": user_id, "email": email})


def _open_enrollments(session: Session, section_id: UUID) -> dict[UUID, Enrollment]:
    """This section's currently-open enrollment windows, keyed by user.

    One row per user by construction: ADR 0023's exclusion constraint refuses two
    overlapping windows for one user and section, and an open window is unbounded
    above, so a second open row for the same pair cannot exist.
    """
    rows = session.scalars(
        select(Enrollment).where(Enrollment.section_id == section_id, Enrollment.ended_on.is_(None))
    )
    return {row.user_id: row for row in rows}


def _record_enrollment(
    session: Session,
    section: Section,
    member: _Member,
    user_id: UUID,
    open_row: Enrollment | None,
    today: date,
) -> None:
    """Open, follow or close one member's enrollment window.

    Three cases, and ADR 0095 is where the rule is written down:

      - **A drop** — `Inactive`, `Deleted`, or absent from the container, which is
        handled by the caller — closes the open window. `ended_on` is the
        extension's end date where the platform supplies one and the sync's own day
        where it does not; `lms_window_end` is the platform's value or nothing.
        Using the sync's day where the platform gave one credits a student for the
        days between.
      - **A member with no open window** is a first sighting or a re-add, and both
        are an `INSERT`. ADR 0023 refuses `UNIQUE (user_id, section_id)` for exactly
        this case: reopening the closed row would lose the weeks the student was
        away.
      - **A member who is still there** has the platform's window followed and
        nothing else touched. `started_on` is a first-seen fact and is never
        rewritten — the grant does not even permit it.

    Every update is conditional on something having changed, which is what makes an
    hourly sync idempotent at row grain (criterion 6) rather than merely at count
    grain.
    """
    if member.dropped:
        if open_row is not None:
            ended = member.window_end.date() if member.window_end is not None else today
            _close(session, open_row, ended_on=ended, window_end=member.window_end)
        return

    if open_row is None:
        try:
            guard_write(table="enrollment", sanction=SANCTION)
        except LmsOwnedWriteRefused:
            logger.exception("the chokepoint refused the roster sync its write to `enrollment`")
            return
        session.execute(
            insert(Enrollment).values(
                user_id=user_id,
                section_id=section.id,
                started_on=today,
                ended_on=None,
                lms_window_start=member.window_start,
                lms_window_end=member.window_end,
            )
        )
        return

    if (
        open_row.lms_window_start == member.window_start
        and open_row.lms_window_end == member.window_end
    ):
        return
    try:
        guard_write(table="enrollment", sanction=SANCTION)
    except LmsOwnedWriteRefused:
        logger.exception("the chokepoint refused the roster sync its write to `enrollment`")
        return
    session.execute(
        update(Enrollment)
        .where(Enrollment.id == open_row.id)
        .values(lms_window_start=member.window_start, lms_window_end=member.window_end)
    )
    session.expire(open_row)


def _close(
    session: Session, open_row: Enrollment, *, ended_on: date, window_end: datetime | None
) -> None:
    """Close one open enrollment window. The recorded transition, in place of a status.

    There is no status column on `enrollment` and there is deliberately not going
    to be one (ADR 0095): the open and closed rows *are* the transition, and a
    status beside them would be a second answer to "was this student enrolled in
    week N" with no rule for choosing between the two.

    `window_end` is only ever the platform's own value. A member who simply vanished
    from the container has no member document to carry one, so the caller passes
    `None` — writing Pulse's own date there is the synthesized window D3 forbids, in
    the one place it is easiest to reach for.
    """
    values: dict[str, Any] = {}
    if open_row.ended_on != ended_on:
        values["ended_on"] = ended_on
    if window_end is not None and open_row.lms_window_end != window_end:
        values["lms_window_end"] = window_end
    if not values:
        return
    try:
        guard_write(table="enrollment", sanction=SANCTION)
    except LmsOwnedWriteRefused:
        logger.exception("the chokepoint refused the roster sync its write to `enrollment`")
        return
    session.execute(update(Enrollment).where(Enrollment.id == open_row.id).values(**values))
    session.expire(open_row)


def _record_the_teaching_instructor(session: Session, section: Section, user_id: UUID) -> None:
    """Grant this section's `INSTRUCTOR` assignment, where the member is a known person.

    D5, and the refusing half is the one that matters. An `INSTRUCTOR`
    `role_assignment` is a purview grant — SPEC §2.1 computes the whole oversight
    surface from these rows — so writing one hands somebody the section's report and
    its moderation view. The person it is granted to has to be somebody Pulse's own
    graph already holds: this module never creates a `person`, because that graph is
    Pulse's (ADR 0024), `person.identity_name` is NOT NULL, and NRPS carries no name
    to fill it with (ADR 0050). A roster instructor nobody has entered gets no
    assignment and a logged skip.

    **`reports_to` is null**, because SPEC §2.1 and ADR 0044 keep supervision edges
    out of E1 — they are E9's admin surface — and an edge invented here would be a
    supervision claim no human made.

    **The row is written through `public.record_teaching_instructor`, not by this
    connection directly** (F2, ADR 0096). This module holds no `INSERT` on
    `role_assignment` any more: a table-wide grant let the application connection
    write a `CARE` row as readily as an `INSTRUCTOR` one, and a grant cannot bound a
    column's value. The definer's body writes `'INSTRUCTOR'` and takes no argument
    for the role, so the value is the database's and not this caller's, and the
    definer is idempotent on its own — it inserts only where no such assignment
    exists.

    **Two idempotence checks and a guard, all kept as defence in depth.** The
    `assignment_scope` read below is E0-11's view (E0-41 keeps it `authz`'s to read),
    the definer re-checks inside its own transaction, and `guard_write` still guards
    the call site — the catalog entry stays, an ADR 0090 layer, not the only one.
    """
    person_id = session.execute(_RESOLVE_PERSON_FOR_USER, {"user_id": user_id}).scalar_one()
    if person_id is None:
        logger.info(
            "a roster instructor of section %s resolves to no person, so no assignment was "
            "written; the people graph is Pulse's own and this sync never adds to it (ADR 0024)",
            section.id,
        )
        return
    if teaching_instructor_assigned(session, person_id=person_id, section_id=section.id):
        return

    try:
        guard_write(
            table="role_assignment",
            assignment_role=AssignmentRole.INSTRUCTOR,
            sanction=SANCTION,
        )
    except LmsOwnedWriteRefused:
        logger.exception(
            "the chokepoint refused the roster sync the teaching instructor's assignment"
        )
        return
    session.execute(_RECORD_TEACHING_INSTRUCTOR, {"person_id": person_id, "section_id": section.id})
