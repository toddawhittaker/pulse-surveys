"""E1-11 — the roster sync: reaching it, the wire it speaks over, and the ground it writes onto.

Five things live here, and each is here rather than in a test module because more
than one module needs it.

**`roster_sync` reaches E1-11's service without naming its entry point.** The
ticket and its work order name the module — `backend/app/services/roster_sync.py`
(D1) — and name exactly one callable in it, `request_section_sync(session,
section_id)` (D9). They do not name the function that syncs one section, nor the
one the hourly job walks every stored address with, so those two are **discovered**
by the roles their parameters play, exactly as `ProvisioningService` in
`fixtures/provisioning.py` discovers E1-10's writer and for the same reason:
naming one here would make the implementer build to this fixture instead of to the
ticket. Every failure below either names a deliverable the ticket asks for and
that is not there, or names an interface question the ticket leaves open.

**`ServiceWire` is the seam the sync's outbound HTTP goes through, and it pins an
interface the implementer has to satisfy.** The work order settles that the client
is `pylti1p3`'s `ServiceConnector`/`NamesRolesProvisioningService` (D11), and that
library takes its transport as a constructor argument —
`ServiceConnector(registration, requests_session=None)`, a `requests.Session`. So
the seam is the library's own, not this suite's invention; what this suite pins is
that the seam reaches the *sync's* caller, because neither an in-process mock
platform's address nor the tool's own resolves over a network here. It is the same
idiom `tests/fixtures/doors.py` uses for the tool's server-side fetches and
`tests/fixtures/client_credentials.py` uses for the platform's, pointed at a third
place. If the sync reaches its platform some other way, the failure below says so
by name and this file is the one place that changes.

**What the wire records is the whole of AC1's evidence.** The mock's Advantage
services deliberately do not require a token — E1-06 ruled that enforcement pairs
with this ticket and the work order's boundary keeps the mock unchanged — so
"the token was attached" cannot be read off a 200 from the roster. It is read off
what the client *sent*: every request the wire carried, with its method, its URL
and its `Authorization` header. `refusing_unauthenticated_reads()` is the other
half, and it is a harness gate rather than the platform's: it answers 401 to a
service read that carries no bearer token, so a client with any unauthenticated
path left in it fails rather than quietly succeeding.

**`composed_roster` serves a roster the test wrote.** The mock's seeded roster is
fixed, and the window, status, email and page-boundary cases E1-11 has to ingest
are not all in it — a re-add across two runs is not expressible at all against a
static seed. So a test may install its own membership container at the section's
address, and `test_the_roster_this_suite_composes_is_the_shape_the_mock_serves`
is the control that keeps that from drifting into a shape no platform sends. The
token exchange stays the mock's throughout: only the roster document is this
suite's.

**`synced_section` seeds the row the sync starts from, committed.** A section
bound to a registered platform's deployment, carrying the stored roster address
SPEC §7.3 has a staff launch record. Seeded rather than launched, deliberately:
what the sync resolves its platform through is `section.lti_deployment_id`
(deferred E1-10 item 1), and a seeded pair of sections on two registered platforms
poses that question directly, where a pair of launches would first have to satisfy
E1-10's parsing, its term lookup and its collision rules.

**The environment these fixtures run under** is `configured_env`'s — the documented
`.env.example` values, laid over the container's database coordinates by
`tool_doors` — and it is stated here because the sync reads `Settings` for nothing
this file can see and `docs/MISTAKES.md` entry 40 is about the suite that ran under
an environment nobody chose. Nothing here reads `os.environ` itself.
"""

import importlib
import inspect
import io
import json
from collections.abc import Callable, Iterator, Mapping, Sequence
from types import ModuleType
from typing import Any
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import pytest

from fixtures.client_credentials import key_pair_from_pem
from fixtures.doors import routed_through
from fixtures.lti_services import NRPS_CLAIM, NRPS_MEDIA_TYPE
from fixtures.supervision import require_column, require_table, single_primary_key

# ---------------------------------------------------------------------------
# Reaching the service.
# ---------------------------------------------------------------------------

# Spelled by E1-11's work order, decision D1: "All sync logic in a new
# `backend/app/services/roster_sync.py`." The package root is `backend/`, so the
# import path is `app.services....`.
ROSTER_SYNC_MODULE = "app.services.roster_sync"

# The one callable the work order spells (D9): "`roster_sync.request_section_sync(
# session, section_id)` skips the enqueue when the section has an `nrps_call` row
# younger than 5 minutes". Named rather than discovered because it is settled.
REQUEST_SECTION_SYNC = "request_section_sync"

# What a value this suite can supply is *for*, matched against a parameter's name.
# Longest alias first, so `requests_session` is the HTTP transport and `session` is
# the database session — the one collision that would otherwise hand the sync a
# `requests.Session` to write rows through.
SYNC_ROLES: dict[str, tuple[str, ...]] = {
    "session": ("session", "db", "db_session"),
    "section_id": ("section_id", "section"),
    "http": ("http", "requests_session", "requests", "http_session", "transport", "client"),
    # The security round's F1: every URL the walk is about to fetch is judged by
    # `refuse_invalid_fetched_address`, and those rules take the environment name.
    # It reaches the sync from `Settings` — never from `os.environ`, which is the
    # read E1-10 item 5 removed from the writer next door — so a test that means to
    # run under a deployment's rules hands the settings it means. A sync that builds
    # its own `Settings()` reads the process environment at call time instead, and
    # `deployment_settings` below sets that too, so either shape is driven by the
    # same fixture (`docs/MISTAKES.md` entry 40: the test states what it runs under).
    "settings": ("settings", "config", "configuration"),
}


class RosterSyncService:
    """E1-11's sync, found rather than named. See the module docstring.

    A fixture that tried call shapes until one stopped raising would swallow a
    `TypeError` raised *inside* the sync and report a design nobody chose as
    working, which is `docs/MISTAKES.md` entry 3. So every lookup here either
    answers or fails with a message naming what it could not find.
    """

    def __init__(self) -> None:
        self._module: ModuleType | None = None

    @property
    def module(self) -> ModuleType:
        """`app.services.roster_sync`, or a failure naming the missing file.

        A `ModuleNotFoundError` for some *other* module is re-raised untouched: a
        sync that exists and imports something absent and a sync that was never
        written need different fixes, and a test must not report them as the same
        thing. `ProvisioningService` draws the same line for the same reason.
        """
        if self._module is None:
            try:
                self._module = importlib.import_module(ROSTER_SYNC_MODULE)
            except ModuleNotFoundError as failure:
                absent = failure.name
                if absent is None or not (
                    absent == ROSTER_SYNC_MODULE or ROSTER_SYNC_MODULE.startswith(f"{absent}.")
                ):
                    raise
                pytest.fail(
                    f"There is no `{ROSTER_SYNC_MODULE}` module. E1-11's work order (D1) puts every "
                    "line of the roster sync in `backend/app/services/roster_sync.py` — the module "
                    "that requests a token with a tool-signed assertion, walks the membership "
                    "container, and writes `user`, `enrollment` and the `INSTRUCTOR` "
                    "`role_assignment` through `guard_write` in the same module. SPEC §13 gives "
                    "`services/` that job."
                )
        return self._module

    def defined_callables(self) -> dict[str, Any]:
        """Every public callable the sync's module defines itself.

        Defines *itself*: a function imported from somewhere else is not part of
        this module's surface, and counting one would let an imported helper answer
        for the ticket's deliverable.
        """
        return {
            name: value
            for name, value in vars(self.module).items()
            if not name.startswith("_")
            and inspect.isfunction(value)
            and getattr(value, "__module__", None) == ROSTER_SYNC_MODULE
        }

    def parameters_of(self, function: Any) -> list[Any]:
        return [
            parameter
            for parameter in inspect.signature(function).parameters.values()
            if parameter.kind not in (parameter.VAR_POSITIONAL, parameter.VAR_KEYWORD)
        ]

    def roles_of(self, function: Any) -> set[str]:
        """Which of `SYNC_ROLES` this function's parameters ask for."""
        found = {self.role_of(parameter.name) for parameter in self.parameters_of(function)}
        return {role for role in found if role is not None}

    @property
    def sync_one_section(self) -> Any:
        """The callable that syncs one section's roster.

        Found by what it *takes* rather than by what it is called, because the work
        order names this function nowhere: it names the module, it names
        `request_section_sync`, and it names the two Celery tasks that wrap the
        service (`sync_rosters` and `sync_section_roster`). A candidate that takes
        a section identifier and is not the debounced enqueue is the one this is.

        Ambiguity stops rather than picks, the contract `ProvisioningService` and
        `SectionCodeService` both keep: two candidates mean this cannot tell which
        one the ticket is about, and choosing would be the test deciding.
        """
        defined = self.defined_callables()
        candidates = {
            name: value
            for name, value in defined.items()
            if name != REQUEST_SECTION_SYNC and "section_id" in self.roles_of(value)
        }
        if len(candidates) > 1:
            narrowed = {name: value for name, value in candidates.items() if "sync" in name.lower()}
            candidates = narrowed or candidates
        if len(candidates) > 1:
            pytest.fail(
                f"`{ROSTER_SYNC_MODULE}` defines more than one public callable that takes a "
                f"section identifier and is not `{REQUEST_SECTION_SYNC}` ({sorted(candidates)}), so "
                "this cannot tell which one syncs a section's roster. E1-11's work order names the "
                "module and the debounced enqueue and leaves this name open, so pinning one here "
                "would settle an interface the ticket does not — say in the pull request which it "
                "is, and `RosterSyncService` in tests/fixtures/roster_sync.py is the one place "
                "that changes."
            )
        if not candidates:
            pytest.fail(
                f"`{ROSTER_SYNC_MODULE}` defines no public callable that takes a section "
                f"identifier — it defines {sorted(defined)}. E1-11's scope: 'the hourly beat job "
                "walking stored addresses; the staff-launch trigger from E1-10 debounced; both "
                "paths converge on one sync routine', and D10 makes "
                "`tasks.sync_section_roster(section_id)` a thin wrapper over it. If the entry "
                "point is there under a shape this cannot see, that is a defect in this fixture "
                "and `SYNC_ROLES` is the line that changes."
            )
        return next(iter(candidates.values()))

    @property
    def sync_every_stored_address(self) -> Any:
        """The callable the hourly job walks every section with a stored address with.

        The counterpart to `sync_one_section`, found the same way and by the same
        rule: it takes no section identifier, because SPEC §7.3 makes the stored
        address the only way the scheduled job learns a section exists.
        """
        defined = self.defined_callables()
        candidates = {
            name: value
            for name, value in defined.items()
            if name != REQUEST_SECTION_SYNC
            and "section_id" not in self.roles_of(value)
            and "session" in self.roles_of(value)
        }
        if len(candidates) > 1:
            narrowed = {name: value for name, value in candidates.items() if "sync" in name.lower()}
            candidates = narrowed or candidates
        if len(candidates) != 1:
            pytest.fail(
                f"`{ROSTER_SYNC_MODULE}` defines {sorted(candidates)} as callables that take a "
                "session and no section identifier, and this needs exactly one: the routine the "
                "hourly job walks every stored address with (D10, "
                "`tasks.sync_rosters`). It defines "
                f"{sorted(defined)}. Say in the pull request which it is if this cannot tell."
            )
        return next(iter(candidates.values()))

    @property
    def request_section_sync(self) -> Any:
        """D9's debounced enqueue, by the name the work order spells."""
        found = self.defined_callables().get(REQUEST_SECTION_SYNC)
        if found is None:
            pytest.fail(
                f"`{ROSTER_SYNC_MODULE}` defines no `{REQUEST_SECTION_SYNC}` — it defines "
                f"{sorted(self.defined_callables())}. E1-11's work order spells this one: "
                "'`roster_sync.request_section_sync(session, section_id)` skips the enqueue when "
                "the section has an `nrps_call` row younger than 5 minutes', and `api/lti.py` "
                "calls it after the launch commit for staff launches that stored an address."
            )
        return found

    @staticmethod
    def role_of(parameter_name: str) -> str | None:
        """Which of `SYNC_ROLES` a parameter called `parameter_name` wants."""
        best: tuple[int, str] | None = None
        for role, aliases in SYNC_ROLES.items():
            for alias in aliases:
                if (parameter_name == alias or parameter_name.endswith(f"_{alias}")) and (
                    best is None or len(alias) > best[0]
                ):
                    best = (len(alias), role)
        return None if best is None else best[1]

    def call(self, function: Any, **available: Any) -> Any:
        """Call `function`, filling each parameter from the roles offered.

        A required parameter no offered role matches stops the test with a message
        naming it. That is either a defect in this fixture or an interface question
        for the ticket, and either way it is something to see rather than route
        around.
        """
        positional: list[Any] = []
        keyword: dict[str, Any] = {}
        for parameter in self.parameters_of(function):
            role = self.role_of(parameter.name)
            if role is None or role not in available:
                if parameter.default is not parameter.empty:
                    continue
                pytest.fail(
                    f"`{getattr(function, '__qualname__', function)}` requires a parameter "
                    f"`{parameter.name}` that this test has nothing to fill from. It is offering "
                    f"{sorted(available)}.\n\n"
                    "If the missing role is the outbound HTTP transport, that is the seam this "
                    "whole suite rests on and it is the library's own: `pylti1p3`'s "
                    "`ServiceConnector(registration, requests_session=…)` takes a "
                    "`requests.Session`, and neither the mock platform's address nor the tool's "
                    "resolves over a network in this process — so a sync that builds its own "
                    "session internally cannot be driven against the mock at all, by this suite or "
                    "by any other. Otherwise add the role to `SYNC_ROLES` in "
                    "tests/fixtures/roster_sync.py once the pull request says what it is for."
                )
                continue
            if parameter.kind is parameter.POSITIONAL_ONLY:
                positional.append(available[role])
            else:
                keyword[parameter.name] = available[role]
        return function(*positional, **keyword)


@pytest.fixture
def roster_sync() -> RosterSyncService:
    """E1-11's sync, reached by discovery. See `RosterSyncService` above."""
    return RosterSyncService()


# ---------------------------------------------------------------------------
# The wire: what the client sent, and what it was answered with.
# ---------------------------------------------------------------------------

# The scope a token for the roster is requested for, spelled as NRPS 2.0 spells it
# and as `tests/integration/test_mock_lms_client_credentials_grant.py` spells it.
# A specification constant, not this suite's choice.
NRPS_MEMBERSHIP_SCOPE = "https://purl.imsglobal.org/spec/lti-nrps/scope/contextmembership.readonly"

# Where the tool publishes the key set the platform verifies a `client_assertion`
# against. E1-06's route, and ADR 0085's "public in every environment".
TOOL_JWKS_PATH = "/lti/jwks"

# The mock platform's own setting for that address — ADR 0084 decision 4: "The
# address is a sixth setting, `MOCK_LMS_TOOL_JWKS_URL`". The platform's name for
# it, not this suite's.
MOCK_LMS_TOOL_JWKS_URL_VARIABLE = "MOCK_LMS_TOOL_JWKS_URL"

# The mock platform's issuer, so two platforms in one test are two registrations
# rather than one row written twice. Spelled as
# `tests/integration/test_registration_endpoints_are_per_platform.py` spells it.
MOCK_LMS_ISSUER_VARIABLE = "MOCK_LMS_ISSUER"

# The query parameters E1-11's work order records the mock refusing with a 400:
# "the mock's NRPS page size is 5 and the mock refuses `role`/`limit`/`rlid`
# filters — the client must not send them." A conformant client asks for the
# container the claim advertised and nothing else.
REFUSED_ROSTER_FILTERS = ("role", "limit", "rlid")

# The bearer scheme, as RFC 6750 spells it.
BEARER = "Bearer"


class ServiceCall:
    """One request the sync made, as it left the client."""

    def __init__(self, method: str, url: str, headers: Mapping[str, str], body: Any) -> None:
        self.method = method
        self.url = url
        self.headers = {name.lower(): value for name, value in headers.items()}
        self.body = body

    @property
    def host(self) -> str | None:
        return urlsplit(self.url).hostname

    @property
    def path(self) -> str:
        return urlsplit(self.url).path

    @property
    def query(self) -> dict[str, list[str]]:
        return parse_qs(urlsplit(self.url).query)

    @property
    def authorization(self) -> str | None:
        return self.headers.get("authorization")

    @property
    def bearer_token(self) -> str | None:
        """The token this request presented, or `None` if it presented none."""
        value = self.authorization or ""
        scheme, _, credential = value.partition(" ")
        return credential.strip() if scheme.lower() == BEARER.lower() and credential else None

    @property
    def form(self) -> dict[str, list[str]]:
        """A form-encoded body, parsed. Empty for a request that carried none."""
        if isinstance(self.body, bytes):
            return parse_qs(self.body.decode("utf-8", "replace"))
        if isinstance(self.body, str):
            return parse_qs(self.body)
        return {}

    def __repr__(self) -> str:
        return f"ServiceCall({self.method} {self.url}, authorization={self.authorization!r})"


class ComposedRoster:
    """A membership container this suite wrote, served in pages at one address.

    The page size is the caller's, so a test can put a member on a page that is
    not the first — `docs/MISTAKES.md` entry 3's shape is a paging test the first
    page satisfies, and AC2 asks for the member the *last* page holds.

    `next_url` replaces the first page's `rel="next"` with an address of the
    caller's choosing, which is the whole of the security round's F1: the walk
    adopts a URL the *platform* chose, and a platform that has been compromised —
    or a mock standing in for one — will point it at `169.254.169.254`. Nothing
    else in this suite can produce that header, because every other next URL is
    built from the URL that was requested.
    """

    def __init__(
        self,
        path: str,
        context_id: str,
        members: Sequence[Mapping[str, Any]],
        size: int,
        next_url: str | None = None,
    ):
        self.path = path
        self.context_id = context_id
        self.members = [dict(member) for member in members]
        self.size = size
        self.next_url = next_url

    @property
    def pages(self) -> list[list[dict[str, Any]]]:
        if not self.members:
            return [[]]
        return [
            self.members[start : start + self.size]
            for start in range(0, len(self.members), self.size)
        ]

    def page_number(self, url: str) -> int:
        numbers = parse_qs(urlsplit(url).query).get("page") or ["1"]
        try:
            return max(1, int(numbers[0]))
        except ValueError:
            return 1

    def document(self, url: str) -> tuple[dict[str, Any], dict[str, str]]:
        """One page of the container, and the headers it is served with."""
        pages = self.pages
        index = min(self.page_number(url), len(pages)) - 1
        split = urlsplit(url)
        body = {
            "id": url,
            "context": {"id": self.context_id},
            "members": pages[index],
        }
        headers = {"content-type": NRPS_MEDIA_TYPE}
        if index == 0 and self.next_url is not None:
            headers["link"] = f'<{self.next_url}>; rel="next"'
        elif index + 1 < len(pages):
            following = f"{split.scheme}://{split.netloc}{split.path}?page={index + 2}"
            headers["link"] = f'<{following}>; rel="next"'
        return body, headers


def _route_key(url: str) -> tuple[str, str]:
    """`url` as the pair a configured answer is filed and looked up under.

    **Host *and* path, since dispute E1-11-04.** A mock platform serves its token
    endpoint at a fixed `/token` path (`mock-lms/app/config.py`), so two platforms
    started under two issuers advertise it at the same path on different hosts.
    Keyed by path alone, a sabotage installed for one platform's `/token`
    answered the *other* platform's `/token` too — so F3's healthy section could
    never obtain a token and "the following section still syncs" was unsatisfiable
    against every implementation. The netloc carries the host and port, which is
    what tells the two apart; the query is dropped, because the token endpoint
    carries none and a paged roster's `?page=` goes through `rosters` rather than
    here.

    `rosters` is *not* keyed this way, and does not need to be: a roster's path
    carries its `{context_id}` (`MEMBERSHIPS_PATH`), and `roster_platforms` gives
    two platforms two different seeded contexts, so their roster paths already
    differ. Only the fixed-path endpoints collide across hosts.
    """
    split = urlsplit(url)
    return (split.netloc, split.path)


class ServiceWire:
    """The `requests.Session` the sync's outbound calls travel over.

    Three jobs, and each is why this is a class rather than a transport function:

      - **route by host** to an in-process application, the way
        `tests/fixtures/doors.py::routed_through` routes the tool's own fetches.
        Nothing rewrites a URL: the registration and the stored roster address
        carry the mock's real advertised addresses, so a client that called
        somewhere nobody registered fails loudly rather than being quietly served.
      - **record every call**, which is the whole of AC1's evidence — see the
        module docstring for why a 200 from the roster is not.
      - **refuse what the ticket forbids**: an unauthenticated service read, and
        the roster filters the mock answers 400 for.
      - **fail an endpoint on request**, so that a test can ask what the sync does
        when the platform is up and one of its two endpoints is not.
    """

    def __init__(self, hosts: Mapping[str, Any]) -> None:
        self.hosts = dict(hosts)
        self.calls: list[ServiceCall] = []
        self.rosters: dict[str, ComposedRoster] = {}
        self.failures: dict[tuple[str, str], int] = {}
        self.answers: dict[tuple[str, str], tuple[int, dict[str, Any]]] = {}
        self.redirects: dict[tuple[str, str], str] = {}
        self.refuse_unauthenticated = False
        self.strip_authorization = False

    # -- what a test installs -----------------------------------------------

    def serve(self, roster: ComposedRoster) -> ComposedRoster:
        """Serve `roster` at its own path instead of passing the request through."""
        self.rosters[roster.path] = roster
        return roster

    def refusing_unauthenticated_reads(self) -> None:
        """Answer 401 to a service read that carries no bearer token.

        **The harness's gate, not the platform's**, and the difference is stated
        rather than hidden. It was written when E1-06's ruling stood and an
        unauthenticated roster read still answered 200 against the real mock;
        E1-11's fix round closed that, so the mock refuses one now too. This gate
        stays, and for a reason the mock's own refusal does not cover: what it
        turns on is the *conformance* question AC1 asks — that the client has no
        unauthenticated path left in it — asserted over the wire the client's own
        requests are recorded on, where a second path can be seen rather than
        inferred from a status code. The mock's refusal is asserted in
        `tests/integration/test_mock_lms_nrps_requires_a_token.py`.
        """
        self.refuse_unauthenticated = True

    def failing(self, url: str, status_code: int) -> None:
        """Answer `status_code` at `url`'s path instead of passing the request through.

        For the one case the mock platform cannot be asked to produce and that
        §6.1's call log exists to make legible: the platform is reachable, the
        roster is there, and the **token endpoint** answers an error. A sync that
        met that and recorded nothing would leave an operator reading a section
        that looks never-synced; one that recorded it against the roster's URL with
        no status would leave a section that looks like a transport failure. Which
        of those it is is a question about the tool's credentials rather than about
        the roster service, and the row is the only place the difference lives.

        Keyed by host and path (`_route_key`), so a failure installed for one
        platform's endpoint does not answer another platform's endpoint at the
        same path — the leak dispute E1-11-04 records.
        """
        self.failures[_route_key(url)] = status_code

    def recovering(self, url: str) -> None:
        """Stop failing `url`, so a test can pose its own control in the same run."""
        self.failures.pop(_route_key(url), None)
        self.answers.pop(_route_key(url), None)
        self.redirects.pop(_route_key(url), None)

    def answering(self, url: str, payload: Mapping[str, Any], status_code: int = 200) -> None:
        """Answer `payload` at `url`'s host and path, with a status this endpoint would use.

        For the security round's F3: a token endpoint that answers 200 with a body
        carrying no `access_token` is a *well-formed* HTTP success that makes
        `pylti1p3` raise `KeyError` reading `response["access_token"]`. That is the
        shape the finding is about — not an error the sync was written to expect,
        but an unexpected exception out of a library, from one platform, in the
        middle of a walk over every section in the institution.

        Keyed by host and path (`_route_key`), and dispute E1-11-04 is why: two
        platforms share the `/token` path, so a sabotage keyed by path alone
        reached both and F3's healthy section could never sync.
        """
        self.answers[_route_key(url)] = (status_code, dict(payload))

    def redirecting(self, url: str, to: str) -> None:
        """Answer a 302 at `url`'s host and path, pointing at `to`.

        F1's other half. A redirect is the same bypass as a hostile `Link` header
        and it arrives one step earlier: the address the walk judged is not the
        address the request ends at, so a client that follows one has validated
        nothing. `requests` follows redirects by default, which is what makes this
        the quiet version.
        """
        self.redirects[_route_key(url)] = to

    def stripping_the_authorization_header(self) -> None:
        """Deliver every service request with its `Authorization` header removed.

        The refused half of AC1's pair. With `refusing_unauthenticated_reads` on,
        this is what proves the gate can fire at all: a run that stays green under
        both is a gate that never refuses anything, and every "the token was
        attached" assertion in this suite would be worth nothing.
        """
        self.strip_authorization = True

    # -- the calls a test reads back ----------------------------------------

    def to(self, path: str) -> list[ServiceCall]:
        return [call for call in self.calls if call.path == path]

    def to_host(self, host: str | None) -> list[ServiceCall]:
        return [call for call in self.calls if call.host == host]

    # -- the transport -------------------------------------------------------

    def session(self) -> Any:
        """A `requests.Session` whose every request goes through `deliver` below."""
        import requests

        built = requests.Session()
        built.mount("http://", _InProcessAdapter(self))
        built.mount("https://", _InProcessAdapter(self))
        return built

    def deliver(self, method: str, url: str, headers: Mapping[str, str], body: Any) -> Any:
        """Answer one request, recording it as the client sent it."""
        delivered = dict(headers)
        if self.strip_authorization:
            for name in [name for name in delivered if name.lower() == "authorization"]:
                del delivered[name]
        self.calls.append(ServiceCall(method, url, delivered, body))

        split = urlsplit(url)
        route = _route_key(url)
        # A configured failure answers before anything else, including the
        # unauthenticated gate: a test that fails an endpoint is asking what the
        # sync does when that endpoint is down, and an answer from any other branch
        # here would be about something else. Matched by host and path (dispute
        # E1-11-04), so a sabotage installed for one platform's endpoint does not
        # answer another platform's endpoint at the same path.
        failing = self.failures.get(route)
        if failing is not None:
            return _Answer(
                failing,
                {"content-type": "application/json"},
                json.dumps({"error": "server_error"}).encode("utf-8"),
            )
        redirected = self.redirects.get(route)
        if redirected is not None:
            return _Answer(
                302,
                {"location": redirected, "content-type": "application/json"},
                b"{}",
            )
        canned = self.answers.get(route)
        if canned is not None:
            status, payload = canned
            return _Answer(
                status,
                {"content-type": "application/json"},
                json.dumps(payload).encode("utf-8"),
            )

        roster = self.rosters.get(split.path)
        presented = {name.lower(): value for name, value in delivered.items()}.get(
            "authorization", ""
        )
        reads_a_service = roster is not None or method.upper() == "GET"
        if (
            self.refuse_unauthenticated
            and reads_a_service
            and not presented.lower().startswith(f"{BEARER.lower()} ")
        ):
            return _Answer(
                401,
                {"content-type": "application/json"},
                json.dumps({"error": "invalid_token"}).encode("utf-8"),
            )
        if roster is not None:
            document, page_headers = roster.document(url)
            return _Answer(200, page_headers, json.dumps(document).encode("utf-8"))

        driver = self.hosts.get(split.hostname or "")
        if driver is None:
            raise RuntimeError(
                f"The roster sync made a request to `{url}`, and no application is mounted at host "
                f"{split.hostname!r} (mounted: {sorted(self.hosts)}). Either the sync resolved its "
                "platform from somewhere other than the section's own `lti_deployment_id` — which "
                "is the failure deferred E1-10 item 1 is about — or this test has to mount the "
                "platform that serves it."
            )
        answered = driver.client.request(method, url, content=body, headers=delivered)
        return _Answer(answered.status_code, dict(answered.headers), answered.content)


class _Answer:
    """One in-process answer, before it is turned into a `requests.Response`."""

    def __init__(self, status_code: int, headers: Mapping[str, str], content: bytes) -> None:
        self.status_code = status_code
        self.headers = dict(headers)
        self.content = content


class _InProcessAdapter:
    """A `requests` transport adapter that answers out of `ServiceWire`.

    A real `requests.Response` is built rather than a stand-in, because
    `pylti1p3.ServiceConnector` reads `r.ok`, `r.json()`, `r.headers` and
    `r.content` off what it gets back, and a duck that got one of those wrong
    would fail inside the library with a message about the library.
    """

    def __init__(self, wire: ServiceWire) -> None:
        self.wire = wire

    def send(self, request: Any, **_: Any) -> Any:
        import requests

        answered = self.wire.deliver(
            request.method, str(request.url), dict(request.headers), request.body
        )
        response = requests.Response()
        response.status_code = answered.status_code
        response.headers.update(answered.headers)
        response.url = str(request.url)
        response.request = request
        response.raw = io.BytesIO(answered.content)
        response._content = answered.content
        response.encoding = "utf-8"
        return response

    def close(self) -> None:
        return None


class _Held:
    """An object with a `.client`, which is all `routed_through` asks of a driver."""

    def __init__(self, client: Any) -> None:
        self.client = client


# ---------------------------------------------------------------------------
# The members a composed roster carries.
# ---------------------------------------------------------------------------

# ADR 0048's namespaced extension, spelled exactly as that record spells it and as
# `tests/integration/test_mock_lms_seed_data.py` reads it. A test may name this
# URI; `backend/` may not — "Nothing in `backend/` may hardcode this URI. It is one
# platform's spelling of one vendor extension, and the tool's side of it is an
# adapter."
ENROLLMENT_EXTENSION = "https://mock-lms.invalid/spec/nrps/enrollment"

# NRPS 2.0's member vocabulary, and the three statuses the specification fixes.
MEMBER_ID = "user_id"
MEMBER_ROLES = "roles"
MEMBER_STATUS = "status"
MEMBER_EMAIL = "email"
ACTIVE = "Active"
INACTIVE = "Inactive"
DELETED = "Deleted"

# The LIS v2 membership vocabulary, as `tests/fixtures/provisioning.py` spells it.
MEMBERSHIP_VOCABULARY = "http://purl.imsglobal.org/vocab/lis/v2/membership#"
INSTRUCTOR_ROLE_URN = f"{MEMBERSHIP_VOCABULARY}Instructor"
LEARNER_ROLE_URN = f"{MEMBERSHIP_VOCABULARY}Learner"

UNSET = object()


def roster_member(
    user_id: str,
    *,
    roles: Sequence[str] = (LEARNER_ROLE_URN,),
    status: str = ACTIVE,
    email: Any = UNSET,
    window: Any = UNSET,
) -> dict[str, Any]:
    """One NRPS member, in the shape ADR 0048 and NRPS 2.0 fix between them.

    `email` and `window` default to *absent* rather than to null, and the
    difference is a criterion rather than a nicety: ADR 0048's amendment seeds one
    member whose "member document omits the key entirely rather than emitting it
    empty", and AC3 is about what that member's enrollment records. An absent key
    and a null one are two different documents and a tool is entitled to treat them
    differently — which is exactly what it must do here.
    """
    member: dict[str, Any] = {
        MEMBER_ID: user_id,
        MEMBER_ROLES: list(roles),
        MEMBER_STATUS: status,
    }
    if email is not UNSET:
        member[MEMBER_EMAIL] = email
    if window is not UNSET:
        member[ENROLLMENT_EXTENSION] = window
    return member


def enrollment_window(start: Any, end: Any = None) -> dict[str, Any]:
    """The extension's own object: `start` required, `end` present and possibly null.

    ADR 0048: "`end` is `null` for a member still enrolled and a timestamp for one
    who dropped. It is present and `null` rather than omitted, because an absent
    key cannot distinguish 'still enrolled' from 'this platform supplies no end
    date'."
    """
    return {"start": start, "end": end}


# ---------------------------------------------------------------------------
# The rows the sync starts from, and the rows it writes.
# ---------------------------------------------------------------------------

# The `lti_platform` column E1-05 added for the token endpoint, spelled as ADR 0036
# keys the registration document and as
# `tests/integration/test_mock_lms_client_credentials_grant.py` spells it.
AUTH_TOKEN_URL_COLUMNS = ("auth_token_url", "token_endpoint", "auth_token_endpoint")

# E1-10's columns on `section`, spelled as `tests/fixtures/provisioning.py` spells
# them: the stored roster address SPEC §7.3 makes the scheduled job's only
# discovery, and the platform's own identifier for the context it came from.
SECTION_ADDRESS_COLUMN = "lms_context_memberships_url"
SECTION_CONTEXT_ID_COLUMN = "lms_context_id"

# E1-11's own table, spelled by the work order's decision D9: "New table
# `nrps_call`: `id` uuid PK, `section_id` FK→section RESTRICT NOT NULL indexed,
# `url` Text NOT NULL, `response_code` int NULL (NULL = transport failure),
# `members_seen` int NULL, `called_at` AwareDateTime NOT NULL."
# What `RosterRows.versioned` labels each row's writing transaction under. A name
# no table declares, so it cannot collide with a column and cannot be mistaken for
# one when a failure prints the row.
ROW_VERSION = "__row_version"

NRPS_CALL_TABLE = "nrps_call"
NRPS_CALL_COLUMNS = frozenset(
    {"id", "section_id", "url", "response_code", "members_seen", "called_at"}
)
CALLED_AT_COLUMN = "called_at"

# `enrollment`'s two new columns, spelled by decision D3: "`lms_window_start:
# AwareDateTime NULL` and `lms_window_end: AwareDateTime NULL` — the ADR 0048
# extension's values verbatim, absent means the platform supplied none". The
# `lms_` prefix is E0-05's rule for a column the platform owns.
WINDOW_START_COLUMN = "lms_window_start"
WINDOW_END_COLUMN = "lms_window_end"

# E0-08's own two, which D3 leaves exactly as they are: Pulse's record of when a
# member was first and last seen by a sync, and the pair ADR 0023's exclusion
# constraint ranges over.
STARTED_ON_COLUMN = "started_on"
ENDED_ON_COLUMN = "ended_on"

# The identity table's two, from the shared `identity_resolution_v001.sql` and
# decision D7. `identity_name` is the one the sync must never write.
IDENTITY_EMAIL_COLUMN = "identity_email"
IDENTITY_NAME_COLUMN = "identity_name"

# `user`'s two, from the same file: the subject key the roster matches against and
# the registration it means anything within.
LMS_USER_ID_COLUMN = "lms_user_id"
USER_PLATFORM_COLUMN = "lti_platform_id"


class SyncedSection:
    """One section, its registered platform, and the address its roster lives at.

    Committed, because the sync may open a connection of its own and because the
    reader below ends its transaction between reads.
    """

    def __init__(
        self,
        rows: Any,
        tables: dict[str, Any],
        platform: Any,
        registration: Any,
        address: str | None,
        context_id: str,
        chain: dict[str, Any],
    ) -> None:
        self.rows = rows
        self.tables = tables
        self.platform = platform
        self.registration = registration
        self.address = address
        self.context_id = context_id
        self.chain = chain
        section = require_table(tables, "section")
        values: dict[str, Any] = {SECTION_CONTEXT_ID_COLUMN: context_id}
        if SECTION_ADDRESS_COLUMN in section.c:
            values[SECTION_ADDRESS_COLUMN] = address
        # The deployment is written explicitly rather than left to the chain,
        # because it is the column the whole ticket turns on: deferred E1-10 item 1
        # makes `section.lti_deployment_id` the only thing that says *whose*
        # credentials this section's roster is fetched with. `seed_row` fills a
        # foreign key from the chain only where the column is NOT NULL, so a
        # nullable one would be left null here and every sync would resolve nothing
        # — which reads as the sync being wrong rather than as this fixture never
        # having bound the section to a platform at all.
        deployment = sorted(
            {
                key.parent.name
                for key in section.foreign_keys
                if key.column.table.name == "lti_deployment"
            }
        )
        if len(deployment) != 1:
            pytest.fail(
                f"`section` has {len(deployment)} foreign keys to `lti_deployment` ({deployment}). "
                "E1-10's round-3 ruling gives a section exactly one, and deferred E1-10 item 1 "
                "makes it how E1-11 resolves the registration to mint a token for."
            )
        self.deployment_column = deployment[0]
        values[self.deployment_column] = registration.deployment_row[
            single_primary_key(require_table(tables, "lti_deployment"))
        ]
        self.row = rows.seed("section", chain, **values)
        rows.commit()

    @property
    def id(self) -> Any:
        return self.row[single_primary_key(require_table(self.tables, "section"))]

    @property
    def host(self) -> str | None:
        return urlsplit(self.address or "").hostname


class RosterRows:
    """What is in the tables E1-11 writes, read on a connection that sees commits.

    Rows rather than counts throughout: AC6 asks for idempotence, and "no row
    changed" is a claim about row identity that a count cannot make (the same shape
    `ProvisionedRows` keeps for E1-10).
    """

    def __init__(self, rows: Any, tables: dict[str, Any]) -> None:
        self.rows = rows
        self.tables = tables

    def table(self, name: str) -> Any:
        return require_table(self.tables, name)

    def all_of(self, name: str) -> list[Any]:
        """Every row of one table, as mappings, after ending the read transaction.

        The transaction is ended first so this connection sees what another one
        committed — the same reason `ProvisionedRows` refreshes.
        """
        self.rows.session.rollback()
        return list(self.rows.session.execute(self.table(name).select()).mappings())

    def versioned(self, name: str) -> list[dict[str, Any]]:
        """Every row of one table, with the transaction that last wrote it.

        **`xmin` is what makes "no row changed" a claim about rows rather than
        about values**, and the difference is a measured one: a mutation battery
        stood an unconditional `UPDATE` on every enrollment the sync re-read — the
        same values written back — and the idempotence test survived it, because
        the comparison it made was over column values and those did not move.

        Postgres does not detect a no-op update. `UPDATE … SET ended_on = ended_on`
        writes a new tuple version with a new `xmin`, so a rewrite that changes
        nothing visible in the row is visible here and nowhere else in this suite.
        What that guards is the production claim the ticket makes — the sync is
        idempotent at row grain — and what it costs in a live database is real:
        every hourly sync rewriting every enrollment in the institution is table
        bloat, autovacuum churn, and a row-version history that says every student
        was touched every hour.

        `ctid` would answer the same question and is not used: it moves when
        `VACUUM` moves a tuple, so it can differ between two reads nothing wrote
        between. `xmin` names the writing transaction and moves only when
        somebody writes.

        Cast to text because `xid` is a type psycopg has no adapter for; the value
        is compared, never interpreted.
        """
        from sqlalchemy import literal_column, select

        self.rows.session.rollback()
        table = self.table(name)
        statement = select(table, literal_column("xmin::text").label(ROW_VERSION))
        return [dict(row) for row in self.rows.session.execute(statement).mappings()]

    def enrollments(self) -> list[Any]:
        return self.all_of("enrollment")

    def users(self) -> list[Any]:
        return self.all_of("user")

    def identities(self) -> list[Any]:
        return self.all_of("user_identity")

    def calls(self) -> list[Any]:
        return self.all_of(NRPS_CALL_TABLE)

    def assignments(self) -> list[Any]:
        return self.all_of("role_assignment")

    def user_for(self, lms_user_id: str) -> Any:
        """The `user` row carrying `lms_user_id`, or `None`."""
        for row in self.users():
            if row.get(LMS_USER_ID_COLUMN) == lms_user_id:
                return row
        return None

    def enrollments_for(self, lms_user_id: str) -> list[Any]:
        """Every enrollment row belonging to the member with this subject key."""
        user = self.user_for(lms_user_id)
        if user is None:
            return []
        key = single_primary_key(self.table("user"))
        link = self.link("enrollment", "user")
        return [row for row in self.enrollments() if row.get(link) == user[key]]

    def identity_for(self, lms_user_id: str) -> Any:
        user = self.user_for(lms_user_id)
        if user is None:
            return None
        key = single_primary_key(self.table("user"))
        link = self.link("user_identity", "user")
        for row in self.identities():
            if row.get(link) == user[key]:
                return row
        return None

    def calls_for(self, section_id: Any) -> list[Any]:
        link = self.link(NRPS_CALL_TABLE, "section")
        return [row for row in self.calls() if row.get(link) == section_id]

    def key(self, name: str) -> str:
        """The name of one table's single primary key column (ADR 0016 makes it one uuid)."""
        return single_primary_key(self.table(name))

    def link(self, name: str, target: str) -> str:
        """The column on `name` whose foreign key points at `target`.

        Followed rather than guessed, for the reason `ProvisionedRows.link` gives:
        `enrollment.user_id` is almost certainly spelled that way, and "almost
        certainly" is how a test ends up filtering on a column that answers `None`
        for every row and reading the empty result as "nothing was written".
        """
        table = self.table(name)
        found = sorted(
            {key.parent.name for key in table.foreign_keys if key.column.table.name == target}
        )
        if len(found) != 1:
            pytest.fail(
                f"`{name}` has {len(found)} foreign keys to `{target}` ({found}); it references "
                f"{sorted({key.column.table.name for key in table.foreign_keys})}. These tests "
                "address rows through that one path."
            )
        return found[0]


@pytest.fixture
def roster_rows(committed_rows: Any, metadata_tables: dict[str, Any]) -> RosterRows:
    """What the sync wrote, read on `committed_rows`'s own connection."""
    return RosterRows(committed_rows, metadata_tables)


@pytest.fixture
def roster_platforms(
    mock_platforms: Any,
    committed_rows: Any,
    metadata_tables: dict[str, Any],
    register_platform: Any,
    tool_doors: Any,
    door_contract: Any,
    stored_signing_key: Any,
) -> Iterator[Callable[..., SyncedSection]]:
    """Start a platform, register it, seed a section on it, and wire the whole loop.

    Everything a conformant service call needs, in one factory, because no part of
    it is separable: the platform verifies the tool's `client_assertion` against
    the key set the tool publishes, the tool publishes the key set out of the
    `tool_signing_key` row, and the sync reaches both over the wire this hands
    back.

    Called more than once it starts a second platform under a second issuer, which
    is what the two-platform test needs — "a test drives two registered platforms,
    each with a section, and asserts each sync presents the assertion of its own
    platform" (deferred E1-10 item 1). Each call seeds its own containment chain,
    so two sections are two courses under two prefixes rather than one row twice.

    **The tool is built once, whatever the platforms**, and it is built at all only
    to serve `/lti/jwks`: the sync is called directly here rather than through a
    door, so nothing else about the application is in the picture. Its environment
    is `tool_doors`'s — `configured_env`'s documented values over the container's
    database coordinates — which is where this suite states what it runs under
    (`docs/MISTAKES.md` entry 40).
    """
    tool = tool_doors({door_contract.settings["public_base_url"]: door_contract.public_base_url})
    tool_jwks_url = f"{door_contract.public_base_url}{TOOL_JWKS_PATH}"
    tool_host = urlsplit(door_contract.public_base_url).hostname or ""
    started: list[SyncedSection] = []
    wire = ServiceWire({})

    def start(issuer: str | None = None, *, address: str | bool = True) -> SyncedSection:
        values = {MOCK_LMS_TOOL_JWKS_URL_VARIABLE: tool_jwks_url}
        if issuer is not None:
            values[MOCK_LMS_ISSUER_VARIABLE] = issuer
        platform = mock_platforms(values)
        # The platform fetches the tool's key set while it verifies an assertion
        # (ADR 0084 decision 4, and the seam `tests/fixtures/client_credentials.py`
        # pins). Installed after the platform's lifespan has run, for the reason
        # that fixture gives, and it replaces the driver's own default: here the
        # key set the platform verifies against is the **real tool's**, served out
        # of the `tool_signing_key` row at `/lti/jwks`.
        platform.application.state.http = routed_through({tool_host: _Held(tool)})
        # So an assertion this driver signs has to be signed with that same row.
        # Without this the platform would refuse it as `invalid_client` — the key
        # is not in the set it just fetched — and every ground-truth roster read
        # in this suite would fail at the mock's NRPS token check rather than say
        # anything about the sync (`docs/MISTAKES.md` entry 22).
        platform.tool_key_pair = key_pair_from_pem("e1-11-stored-tool-key", stored_signing_key)

        contexts = platform.seeded_contexts()
        assert contexts, (
            "The mock platform offers no launch, so it advertises no context memberships URL and "
            "there is no roster address to store on a section. E0-14 seeds the launches and E0-15 "
            "the roster behind them."
        )
        context = contexts[len(started) % len(contexts)]
        registration = register_platform(
            platform.require_offers()[0],
            (platform.discovery() or {}).get("jwks_uri") or "",
            None,
        )
        token_url = (platform.discovery() or {}).get("token_endpoint")
        assert isinstance(token_url, str) and token_url, (
            "The mock platform's discovery document advertises no `token_endpoint`, so there is no "
            "address to register under `auth_token_url` and no token this sync could request. "
            "E1-06 adds it; `test_mock_lms_client_credentials_grant.py` is where its absence is "
            "diagnosed."
        )
        registration.rewrite(
            registration.platform_table,
            registration.platform_row,
            require_column(registration.platform_table, AUTH_TOKEN_URL_COLUMNS),
            token_url,
        )

        served = context.memberships_url if address is True else address
        chain = {
            "lti_platform": registration.platform_row,
            "lti_deployment": registration.deployment_row,
        }
        section = SyncedSection(
            committed_rows,
            metadata_tables,
            platform,
            registration,
            None if served is False else str(served),
            context.context_id,
            chain,
        )
        started.append(section)
        if section.host:
            wire.hosts[section.host] = platform
        wire.hosts[urlsplit(token_url).hostname or ""] = platform
        return section

    start.wire = wire  # type: ignore[attr-defined]
    start.tool = tool  # type: ignore[attr-defined]
    yield start


@pytest.fixture
def service_wire(roster_platforms: Any) -> ServiceWire:
    """The wire every platform this test started is reachable over."""
    return roster_platforms.wire


@pytest.fixture
def synced_section(roster_platforms: Any) -> SyncedSection:
    """One registered platform, and one section carrying its roster address."""
    return roster_platforms()


@pytest.fixture
def stored_signing_key(committed_rows: Any, metadata_tables: dict[str, Any]) -> str:
    """One `tool_signing_key` row, so the tool has something to sign with.

    E1-05 puts the tool's private key in that table and E1-06 publishes its public
    half; D11 has E1-11 sign its `client_assertion` with the same row, through one
    construction path for inbound and outbound. Generated per run and never written
    down, which is SPEC §9.1's rule — the same shape
    `tests/integration/test_the_tool_publishes_its_key_set.py` uses, and it is
    deliberately a separate row from that module's so neither test depends on the
    other's ordering.
    """
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    table = "tool_signing_key"
    if table not in metadata_tables:
        pytest.fail(
            f"There is no `{table}` table (there are {sorted(metadata_tables)}). E1-05 adds it, "
            "E1-06 publishes the key set out of it, and D11 signs this ticket's client assertion "
            "with the same row — without it nothing here can request a token at all."
        )
    existing = list(
        committed_rows.session.execute(require_table(metadata_tables, table).select()).mappings()
    )
    if existing:
        return str(existing[0]["private_key_pem"])
    pem = (
        rsa.generate_private_key(public_exponent=65537, key_size=2048)
        .private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        .decode("ascii")
    )
    committed_rows.seed(table, {}, private_key_pem=pem)
    committed_rows.commit()
    return pem


@pytest.fixture
def a_section_with_no_address(
    committed_rows: Any, metadata_tables: dict[str, Any]
) -> Callable[[SyncedSection], Any]:
    """A second section under the same registration, carrying no roster address.

    SPEC §7.3's never-synced state: "Where a platform withholds the address even
    from a staff launch, the section has no roster and no sync can be attempted:
    the admin console shows it as never-synced (§6.1, §6.3) rather than as empty,
    because a section with no roster and a section with no enrollments are
    different states and only one of them is a fault."

    Seeded beside a section that *does* carry one, under the same deployment and
    the same course, so the only difference between the two is the address — which
    is what makes the discovery assertion about the address rather than about
    anything else the two rows might not share.
    """

    def seed(beside: SyncedSection) -> Any:
        row = committed_rows.seed(
            "section",
            dict(beside.chain),
            **{
                SECTION_CONTEXT_ID_COLUMN: f"never-synced-{uuid4().hex[:12]}",
                SECTION_ADDRESS_COLUMN: None,
            },
        )
        committed_rows.commit()
        return row[single_primary_key(require_table(metadata_tables, "section"))]

    return seed


@pytest.fixture
def seed_a_member(
    committed_rows: Any, metadata_tables: dict[str, Any], roster_rows: RosterRows
) -> Callable[..., dict[str, Any]]:
    """Put a member's `user` and `enrollment` rows in the database out of band.

    Two tests need a member the sync did **not** put there, and they need it for
    different reasons.

    `docs/MISTAKES.md` entry 31 is the first: "'Running it twice is safe' was
    tested only against a database the loader itself had filled." A sync that
    inserts on the first run and matches its own rows on the second is idempotent
    against its own output and can still duplicate every row it meets in a
    database it did not fill — which is every database after the first hour.

    The second is arithmetic. ADR 0023 puts a check constraint on `enrollment`
    (`ended_on IS NULL OR ended_on >= started_on`), so a member first seen today
    and dropped by the platform last week cannot be recorded at all — the drop and
    re-add cases need a first sighting that is genuinely older than the end date
    the platform sends, and only a row seeded out of band can have one.

    Every column is named by following a foreign key rather than by guessing at a
    name, through the same helper the reader uses.
    """

    def seed(
        section: SyncedSection,
        subject: str,
        *,
        started_on: Any,
        ended_on: Any = None,
        window_start: Any = None,
        window_end: Any = None,
    ) -> dict[str, Any]:
        enrollment = require_table(metadata_tables, "enrollment")
        missing = [
            name
            for name in (WINDOW_START_COLUMN, WINDOW_END_COLUMN, STARTED_ON_COLUMN, ENDED_ON_COLUMN)
            if name not in enrollment.c
        ]
        if missing:
            pytest.fail(
                f"`enrollment` declares no {missing} (it declares "
                f"{[column.name for column in enrollment.columns]}). E1-11's work order (D3) adds "
                "`lms_window_start` and `lms_window_end` as nullable `AwareDateTime` columns "
                "carrying the ADR 0048 extension's values verbatim, beside E0-08's `started_on` "
                "and `ended_on`, which keep their meaning as Pulse's own record of when a member "
                "was first and last seen by a sync. Without them there is nowhere to record the "
                "difference SPEC §3.4 reads."
            )
        user = committed_rows.seed(
            "user",
            dict(section.chain),
            **{
                LMS_USER_ID_COLUMN: subject,
                roster_rows.link("user", "lti_platform"): section.registration.platform_row[
                    single_primary_key(require_table(metadata_tables, "lti_platform"))
                ],
            },
        )
        enrollment = committed_rows.seed(
            "enrollment",
            dict(section.chain),
            **{
                roster_rows.link("enrollment", "user"): user[
                    single_primary_key(require_table(metadata_tables, "user"))
                ],
                roster_rows.link("enrollment", "section"): section.id,
                STARTED_ON_COLUMN: started_on,
                ENDED_ON_COLUMN: ended_on,
                WINDOW_START_COLUMN: window_start,
                WINDOW_END_COLUMN: window_end,
            },
        )
        committed_rows.commit()
        return {"user": user, "enrollment": enrollment}

    return seed


@pytest.fixture
def compose_a_roster() -> Callable[..., ComposedRoster]:
    """Build a membership container this test wrote, for one section's address."""

    def build(
        section: SyncedSection,
        members: Sequence[Mapping[str, Any]],
        size: int = 5,
        next_url: str | None = None,
    ) -> ComposedRoster:
        return ComposedRoster(
            urlsplit(section.address or "").path,
            section.context_id,
            members,
            size,
            next_url,
        )

    return build


# The environment name the fetched-address rules are in force under, and a
# platform address that passes them. **Both are forced by ADR 0081 rather than
# chosen here**: every rule that record writes is "switched off where `ENVIRONMENT`
# is exactly the development name", so a test of a refusal has to run somewhere a
# refusal happens; and rule 1 refuses cleartext that leaves this machine, so the
# platform a *legitimate* page is fetched from has to be `https`. Nothing is
# actually encrypted — the wire answers in process — but the scheme is what the
# rule reads, and posing the accepted half over `http` would make it a test of the
# transport rule instead of a test of the address.
A_DEPLOYMENT = "production"
HTTPS_PLATFORM_ISSUER = "https://roster-platform.invalid"

# Two addresses a fetched URL may never reach, and one it may. `169.254.169.254`
# is ADR 0081 rule 4's own subject — "where the cloud metadata service answers
# credentials to any request that reaches it on every major provider" — and rule 4
# arrived in E1-10's round-3 review for exactly this reason. The loopback entry is
# the SSRF that rule 3 does *not* cover, because that rule is about an address a
# *browser* resolves: a fetched loopback URL is resolved by this container, which
# is the opposite case and the classic one. `10.0.0.5` is the acceptance ADR 0081
# stakes rule 4 on — "`169.254.169.254` refused and `10.0.0.5` accepted is one line
# apart in the implementation and a product difference in the field".
CLOUD_METADATA_HOST = "169.254.169.254"
LOOPBACK_HOST = "127.0.0.1"
PRIVATE_RANGE_HOST = "10.0.0.5"


@pytest.fixture
def deployment_settings(monkeypatch: pytest.MonkeyPatch, configured_env: dict[str, str]) -> Any:
    """A `Settings` whose environment is a deployment's, with the process agreeing.

    Two things at once, deliberately. The settings object is what a sync that
    *takes* one is handed, and the process variable is what a sync that builds its
    own `Settings()` reads at call time — so a test using this states the
    environment it runs under whichever way the sync reaches it
    (`docs/MISTAKES.md` entry 40), and neither shape can quietly run under
    development's "everything is accepted".

    `configured_env` first, so every documented variable has a value before
    `Settings()` is constructed; then `ENVIRONMENT` is overwritten. The name is
    asserted to be a deployment through `app.config`'s own predicate rather than
    assumed, because a value that turned out to be the development name would
    switch every rule under test off and leave the refusals below passing for
    having nothing to refuse.
    """
    from app.config import DEVELOPMENT_ENVIRONMENT, Settings

    assert A_DEPLOYMENT != DEVELOPMENT_ENVIRONMENT, (
        f"`{A_DEPLOYMENT}` is this build's development environment name, so the address rules "
        "would be switched off (ADR 0081: 'every one of them switched off where `ENVIRONMENT` is "
        "exactly the development name') and every refusal in these tests would pass against a "
        "validator that refuses nothing."
    )
    monkeypatch.setenv("ENVIRONMENT", A_DEPLOYMENT)
    return Settings()


@pytest.fixture
def a_subject() -> Callable[[str], str]:
    """A subject key nothing else in this run uses.

    Fresh per call, because the sync matches a member to a `user` row by
    `(lti_platform_id, lms_user_id)` and a value reused across tests would let one
    test's row satisfy another's assertion.
    """

    def build(label: str) -> str:
        return f"e1-11-{label}-{uuid4().hex[:12]}"

    return build


@pytest.fixture
def roster_contract() -> Any:
    """The names E1-11's test modules read the sync's work through.

    Handed over as a fixture rather than imported, for the reason every fixtures
    module in this suite gives: an import of a fixtures module by name depends on
    where pytest put `tests/` on `sys.path`, and an import error is not a red.
    """

    class RosterContract:
        extension = ENROLLMENT_EXTENSION
        member_id = MEMBER_ID
        member_roles = MEMBER_ROLES
        member_status = MEMBER_STATUS
        member_email = MEMBER_EMAIL
        active = ACTIVE
        inactive = INACTIVE
        deleted = DELETED
        instructor_role_urn = INSTRUCTOR_ROLE_URN
        learner_role_urn = LEARNER_ROLE_URN

        nrps_call_table = NRPS_CALL_TABLE
        nrps_call_columns = NRPS_CALL_COLUMNS
        called_at_column = CALLED_AT_COLUMN
        window_start_column = WINDOW_START_COLUMN
        window_end_column = WINDOW_END_COLUMN
        started_on_column = STARTED_ON_COLUMN
        ended_on_column = ENDED_ON_COLUMN
        identity_email_column = IDENTITY_EMAIL_COLUMN
        identity_name_column = IDENTITY_NAME_COLUMN
        lms_user_id_column = LMS_USER_ID_COLUMN
        user_platform_column = USER_PLATFORM_COLUMN
        section_address_column = SECTION_ADDRESS_COLUMN

        membership_scope = NRPS_MEMBERSHIP_SCOPE
        refused_filters = REFUSED_ROSTER_FILTERS
        nrps_claim = NRPS_CLAIM
        jwks_path = TOOL_JWKS_PATH

        a_deployment = A_DEPLOYMENT
        https_platform_issuer = HTTPS_PLATFORM_ISSUER
        cloud_metadata_host = CLOUD_METADATA_HOST
        loopback_host = LOOPBACK_HOST
        private_range_host = PRIVATE_RANGE_HOST

        member = staticmethod(roster_member)
        window = staticmethod(enrollment_window)

    return RosterContract()
