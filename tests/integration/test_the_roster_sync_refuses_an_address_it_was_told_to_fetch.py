"""Every URL the walk fetches is judged, not only the one that was stored — E1-11's F1.

The security review's HIGH. A roster walk does not fetch one address: it fetches
the stored one, and then whatever the platform's `Link: rel="next"` header names,
and then whatever *that* page's header names, each with the tool's Bearer token
attached. E1-10 judged the stored address against
`app.models.lti.refuse_invalid_fetched_address` — rule 4 of ADR 0081 was that
round's own addition, aimed by name at `169.254.169.254`, "where the cloud
metadata service answers credentials to any request that reaches it on every major
provider" — and the walk then adopts an address chosen by the platform and judges
none of it. The rule is defeated one level out, by a header.

**What a compromised or hostile platform gets, unfixed.** One `Link` header and
this container issues an authenticated GET to any address it can route to: a cloud
metadata endpoint, a service on the loopback interface, anything inside the
network the worker sits in. The response is parsed as a membership container, so
the blast radius is not only the request — a metadata document that happens to
parse becomes roster members.

**So the fix is one sentence and the tests are its boundary**: every URL the walk
is about to fetch passes the same rules the stored one does, and a URL that fails
is recorded as a refusal and stops the walk. The redirect case is the same bypass
arriving a step earlier — the address that was judged is not the address the
request ends at — so redirect following is off.

**These tests run under a deployment's `ENVIRONMENT`, and they have to.** ADR 0081:
"every one of them switched off where `ENVIRONMENT` is exactly the development
name." A refusal test under development would pass against a validator that refuses
nothing, which is `docs/MISTAKES.md` entry 3 in the one place this file cannot
afford it. `deployment_settings` sets the process variable and hands back the
`Settings` a sync that takes one is given, so the environment is stated whichever
way the sync reads it (entry 40).

**The platform is reached over `https` here, unlike everywhere else in this
suite.** Rule 1 refuses cleartext that leaves this machine, so an `http` platform
under a deployment would be refused at the *first* page and the accepted half of
every pair below would be untestable. Nothing is encrypted — the wire answers in
process — but the scheme is what the rule reads.

**The cleanup batch adds two things to this module's subject, and both are about
the same sentence: the address that was judged has to be the address the request
goes to.** Rule 5 resolves each fetched URL's host and refuses any returned
address that is not globally routable, which closes the residual finding E1-11
recorded — an internal service holding a valid certificate on a private or
split-horizon address passes every rule that reads a *spelling*. And the pin
closes the gap between the check and the connection: a name resolved twice can
answer differently the second time, so the sync connects to the address it
judged, under the hostname it judged it for.

**Every hostname these tests drive is answered by an injected resolver, never by
DNS.** `roster-platform.invalid` resolves nowhere, so a sync that reached a name
server would be red here for a reason that has nothing to do with the rules
(`docs/MISTAKES.md` entry 40's shape). `resolving` builds the stub and records
what was asked of it, which is how "nothing was resolved" becomes an assertion
rather than an absence.

**One test in this module runs under the development name, deliberately**, and
says so in its own docstring: the exemption that keeps a development stack from
resolving its own roster host only exists there, so it cannot be posed anywhere
else.
"""

from typing import Any
from urllib.parse import urlsplit

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.lti]

# Where a hostile `Link` header points. Built as absolute URLs on hosts ADR 0081
# names, because that is what a header carries; the path is arbitrary and the host
# is the whole subject.
METADATA_URL = "http://169.254.169.254/latest/meta-data/iam/security-credentials/"
LOOPBACK_URL = "http://127.0.0.1:9/memberships"

# Where the second page of a two-host walk is served from. A path of its own, so
# the wire can answer it without the second host being mounted — a roster is
# looked up by path, and the point of these tests is which *address* the request
# went to rather than which application answered it.
SECOND_PAGE_PATH = "/rosters/second-host-page"


@pytest.fixture
def platform_on_https(roster_platforms: Any, roster_contract: Any) -> Any:
    """One registered platform whose advertised addresses pass rule 1 under a deployment."""
    return roster_platforms(roster_contract.https_platform_issuer)


@pytest.fixture
def resolving_the_platform(resolving: Any, platform_on_https: Any, roster_contract: Any) -> Any:
    """A resolver answering this section's own host with a globally-routable address.

    Every sync driven below starts by judging the section's *stored* address, and
    under a deployment rule 5 resolves it — there is no exemption outside
    development. So without this every test in the module would refuse at the
    first page, and every refusal assertion would be green for the wrong reason.

    Tests that drive a second host add it with `.answering(host, addresses)`.
    """
    return resolving({platform_on_https.host: (roster_contract.a_global_address,)})


def roster_gets(wire: Any, section: Any) -> list[Any]:
    """Every GET the sync made for a roster page of `section`, in order."""
    path = urlsplit(section.address or "").path
    return [call for call in wire.calls if call.method.upper() == "GET" and call.path == path]


def sync(
    roster_sync: Any,
    section: Any,
    wire: Any,
    rows: Any,
    settings: Any,
    resolve: Any = None,
) -> BaseException | None:
    """Run one section's sync, answering the exception it raised or `None`.

    Whether the sync raises or returns on a refusal is deliberately not asserted
    anywhere in this module: ADR 0090's consequences leave that to the writer — "a
    later sanctioned writer running on a job rather than on a request may
    reasonably want the opposite: fail loudly, let the task retry". What is
    asserted is the row it leaves and the rows it does not write, which is the same
    contract the token-refusal test next door holds.

    `resolve` is offered only when a test supplies one, so a build whose sync does
    not take the parameter yet is driven exactly as it was before — and a build
    that renamed it is caught by
    `test_the_sync_takes_the_resolution_seam_this_suite_injects` rather than by
    thirty tests going quietly to real DNS.
    """
    available: dict[str, Any] = {
        "session": rows.session,
        "section_id": section.id,
        "http": wire.session(),
        "settings": settings,
    }
    if resolve is not None:
        available["resolve"] = resolve
    try:
        roster_sync.call(roster_sync.sync_one_section, **available)
        rows.commit()
    except Exception as failure:
        rows.session.rollback()
        return failure
    return None


# ---------------------------------------------------------------------------
# Controls. **A red here means these tests are broken, not the sync.**
# ---------------------------------------------------------------------------


def test_the_wire_advertises_the_hostile_next_url_verbatim(
    platform_on_https: Any,
    service_wire: Any,
    compose_a_roster: Any,
    roster_contract: Any,
    a_subject: Any,
    link_relations_in: Any,
) -> None:
    """The header the refusal tests rest on is proven to exist before they are believed.

    Every refusal below is "the walk stopped and fetched nothing hostile". That is
    equally true of a container advertising **no** next page at all — the walk
    would stop because there was nowhere to go, and the test would report a
    validator that does not exist as working (`docs/MISTAKES.md` entry 3, and
    entry 35: a guard that only ever reports absence).

    So the composed roster's first page is fetched here directly and its `Link`
    header read with E0-15's own parser — the same function the sync's library
    scrapes the relation with — and required to name the hostile URL exactly.

    **A red here means these tests are broken, not the sync.**
    """
    service_wire.serve(
        compose_a_roster(
            platform_on_https,
            [roster_contract.member(a_subject("control"))],
            next_url=METADATA_URL,
        )
    )
    answered = service_wire.session().get(str(platform_on_https.address))

    assert answered.status_code == 200, (
        f"The composed roster answered {answered.status_code} at the section's own address, so "
        "there is no first page for a hostile header to be attached to."
    )
    relations = link_relations_in(answered.headers.get("link"))
    assert relations.get("next") == METADATA_URL, (
        f"The first page advertises `next` as {relations.get('next')!r} and this test needs "
        f"{METADATA_URL!r} — its whole `Link` header is {answered.headers.get('link')!r}. Without "
        "that relation the walk has nowhere hostile to go, and every refusal below would pass "
        "against a sync that validates nothing."
    )


def test_the_wire_answers_a_redirect_a_following_client_would_take(
    platform_on_https: Any, service_wire: Any, roster_contract: Any
) -> None:
    """The 302 the redirect test rests on, proven to be one a client would follow.

    `requests` follows redirects by default, so "the sync did not end up at the
    metadata endpoint" is satisfied by a harness whose redirect was never a
    redirect at all. This drives the same wire with following turned **on** and
    requires it to arrive at the target — which is exactly what the sync must not
    do.

    **A red here means these tests are broken, not the sync.**
    """
    service_wire.redirecting(str(platform_on_https.address), METADATA_URL)
    service_wire.answering(METADATA_URL, {"members": [], "id": "the-metadata-endpoint"})

    followed = service_wire.session().get(str(platform_on_https.address), allow_redirects=True)

    assert followed.status_code == 200 and followed.json().get("id") == "the-metadata-endpoint", (
        f"A client following redirects reached {followed.status_code} / {followed.text[:120]!r} "
        "rather than the redirect's target. The harness's 302 is then not one anybody would "
        "follow, and the refusal below would be about nothing."
    )
    assert roster_contract.cloud_metadata_host in METADATA_URL, (
        f"The URL this module redirects to ({METADATA_URL!r}) does not name "
        f"{roster_contract.cloud_metadata_host!r}, the host ADR 0081 rule 4 is written about — so "
        "a sync that followed the redirect would land somewhere the rules might legitimately "
        "allow, and the refusal would be asserting the wrong thing."
    )


# ---------------------------------------------------------------------------
# F1 — the pair, on each of the two hostile classes.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("hostile", "why"),
    [
        pytest.param(METADATA_URL, "the cloud metadata service", id="link-local"),
        pytest.param(LOOPBACK_URL, "a service on this container's own loopback", id="loopback"),
    ],
)
def test_a_next_page_the_platform_points_off_its_own_host_is_refused(
    roster_sync: Any,
    platform_on_https: Any,
    service_wire: Any,
    compose_a_roster: Any,
    committed_rows: Any,
    roster_rows: Any,
    roster_contract: Any,
    deployment_settings: Any,
    resolving_the_platform: Any,
    a_subject: Any,
    hostile: str,
    why: str,
) -> None:
    """F1's refused half, on both classes of address the rules exist for.

    **The mutation this kills**: the walk loop adopting `next_page_url` and
    fetching it — which is what `pylti1p3`'s own `get_members()` does and what this
    sync does today. Nothing else in this suite mentions it: the paging test
    asserts the *last* page's member arrives, the conformance test asserts a token
    was attached, and both are satisfied by a client that will fetch anything the
    platform names.

    **Two classes, parametrised, because they fail different rules and an
    implementation can close one and leave the other.** `169.254.169.254` is ADR
    0081 rule 4's own subject, added in E1-10's round-3 review. The loopback case
    is the one that rule does *not* cover — rule 3 refuses loopback on
    `authorization_endpoint` alone, on the argument that "that string is never
    resolved in this container", which is precisely untrue of a URL the walk
    fetches. A fetched loopback address reaches whatever this container is running
    beside, which is the textbook SSRF and the reason the fix says *every* fetched
    URL rather than *the same rules*.

    **Three assertions, and the third is the one that makes this a security
    property rather than a paging one.** The walk stops; a call row records the
    refusal, so an operator reading §6.1's console sees a platform sending
    addresses this tool will not fetch rather than a section that silently stopped
    growing; and no member from the hostile page is ingested. The first page's own
    member *is* ingested — the refusal is per URL, and a walk that threw the whole
    container away on a bad second page would lose a class that synced correctly
    up to it.
    """
    reachable = a_subject("first-page")
    service_wire.serve(
        compose_a_roster(
            platform_on_https,
            [roster_contract.member(reachable)],
            next_url=hostile,
        )
    )

    sync(
        roster_sync,
        platform_on_https,
        service_wire,
        committed_rows,
        deployment_settings,
        resolve=resolving_the_platform,
    )

    fetched = [call.url for call in service_wire.calls if call.url == hostile]
    assert not fetched, (
        f"The sync fetched {hostile!r} — {why} — because a platform's `Link` header named it. The "
        "tool's Bearer token went with it, and whatever answered was parsed as a membership "
        "container. ADR 0081 rule 4 refuses that address on the columns a *stored* row makes this "
        "container fetch; the walk fetches an address the platform chose at run time, and the fix "
        "is that both go through `refuse_invalid_fetched_address`."
    )
    recorded = roster_rows.calls_for(platform_on_https.id)
    assert len(recorded) >= 2, (
        f"The section's `nrps_call` rows are {[dict(row) for row in recorded]}. The refused page is "
        "a call the tool decided not to make, and §6.1's console is where an operator learns that a "
        "platform is advertising addresses this tool refuses — with no row, the section reads as "
        "one whose roster simply ended."
    )
    assert not [
        row for row in recorded if row.get("url") == hostile and row.get("response_code") == 200
    ], (
        f"A call row records a 200 against {hostile!r}: {[dict(row) for row in recorded]}. That "
        "page was never fetched, so nothing answered it — a 200 here means either the refusal was "
        "recorded as a success or the address was fetched after all.\n\n"
        "*Which* code a refusal carries is left loose here and is not open anywhere: ADR 0096 "
        "settles it as NULL, and "
        "`test_a_development_stack_refuses_a_hop_off_its_own_host_that_resolves_privately` pins "
        "that — this row asserts only that it is not a 200, so a change to the sentinel goes red "
        "in one place rather than two."
    )

    # F1-4: the read-back channel is closed too. It is not enough that the tool
    # declined to *fetch* the hostile URL — the URL the platform chose must not
    # reach the `nrps_call.url` column either, because §6.1's console is read per
    # section and a row carrying `169.254.169.254` puts an attacker's string on an
    # operator's screen and detaches the record from the section's own address.
    stored_address = str(platform_on_https.address)
    assert not [row for row in recorded if row.get("url") == hostile], (
        f"An `nrps_call` row carries the hostile URL {hostile!r} in its `url` column: "
        f"{[dict(row) for row in recorded]}. The refusal must be recorded against the section's "
        f"own stored address ({stored_address!r}), not against the address the platform chose in "
        "its `Link` header — a row keyed to `following` hands the console a value an attacker "
        "supplied and reads as a call to somewhere this tool never meant to go.\n\n"
        "**The mutation this kills**: recording the refusal against `following` (the scraped "
        "`rel=next` URL) instead of the section's stored address."
    )
    refusals = [row for row in recorded if row.get("response_code") != 200]
    assert refusals, (
        f"No `nrps_call` row records the refusal itself — the section's rows are "
        f"{[dict(row) for row in recorded]}. The refused page is a call the tool decided not to "
        "make, and it is a distinct row from the first page's 200."
    )
    assert all(row.get("url") == stored_address for row in refusals), (
        f"A refusal row is keyed to something other than the section's stored address "
        f"({stored_address!r}): {[dict(row) for row in refusals]}. SPEC §7.3 makes that stored "
        "address the section's identity on the console, and D9's call log is read against it — a "
        "refusal recorded under the platform-chosen URL is a refusal an operator cannot tie back "
        "to the section it belongs to."
    )

    assert roster_rows.enrollments_for(reachable), (
        "The first page's member was not ingested. The refusal is per URL: a walk that discards "
        "the whole container because its *second* page was hostile loses a class that synced "
        "correctly up to the boundary, and every hourly run would lose it again."
    )


def test_a_legitimate_next_page_on_the_platforms_own_host_still_walks_to_the_last(
    roster_sync: Any,
    platform_on_https: Any,
    service_wire: Any,
    compose_a_roster: Any,
    committed_rows: Any,
    roster_rows: Any,
    roster_contract: Any,
    deployment_settings: Any,
    resolving_the_platform: Any,
    a_subject: Any,
) -> None:
    """F1's accepted half — the one no refusal test can stand without.

    A validator that refused every fetched URL passes both refusal cases above
    perfectly and syncs one page of every class in the institution, for ever. That
    is the cheapest wrong implementation of this fix and the only thing that
    catches it is an accepted case: three members over two pages, on the platform's
    own `https` host, all three ingested.

    **The near miss it is written around**: the second page's URL differs from the
    first only in its query, which is what a real platform's `rel="next"` looks
    like. An implementation that refused any URL that was not *equal* to the stored
    address would pass every other test in this module and fail here.

    **It also holds the environment honest.** These members are ingested under a
    deployment's `ENVIRONMENT`, where ADR 0081's rules are in force — so a green
    here says the rules accept a legitimate address rather than that the test found
    a configuration where nothing is judged.
    """
    members = [a_subject("page-one"), a_subject("page-two"), a_subject("page-two-second")]
    service_wire.serve(
        compose_a_roster(
            platform_on_https,
            [roster_contract.member(subject) for subject in members],
            size=1,
        )
    )

    failure = sync(
        roster_sync,
        platform_on_https,
        service_wire,
        committed_rows,
        deployment_settings,
        resolve=resolving_the_platform,
    )

    assert failure is None, (
        f"A walk over a legitimate two-page roster on the platform's own host raised {failure!r}. "
        "Under a deployment's environment ADR 0081's rules are in force, and an address on the "
        "platform's own `https` host is one they accept — a refusal here is the fix refusing "
        "everything, which passes every hostile case in this module and syncs one page of every "
        "class."
    )
    for subject in members:
        assert roster_rows.enrollments_for(subject), (
            f"{subject!r} was not ingested from a three-member roster paged one member at a time. "
            f"The pages the sync fetched were "
            f"{[call.url for call in service_wire.calls if call.method.upper() == 'GET']}."
        )


def test_a_page_that_answers_a_redirect_is_refused_rather_than_followed(
    roster_sync: Any,
    platform_on_https: Any,
    service_wire: Any,
    compose_a_roster: Any,
    committed_rows: Any,
    roster_rows: Any,
    roster_contract: Any,
    deployment_settings: Any,
    resolving_the_platform: Any,
    a_subject: Any,
) -> None:
    """The same bypass, arriving before any header is read.

    Judging a URL and then following whatever redirect it answers validates
    nothing: the address that passed the rules is not the address the request ends
    at. `requests` follows redirects by default, so this is the version that needs
    no hostile header and no compromised platform — a misconfigured reverse proxy
    in front of a real LMS is enough.

    **The mutation this kills**: leaving redirect following at its default on the
    sync's session. The control above proves the harness's 302 is one a following
    client takes, so a green here is the sync declining rather than the redirect
    being inert.

    **The pair is the accepted case in this module**: with no redirect in the way,
    the same platform's pages are fetched and ingested. Without it, "did not reach
    the target" would be satisfied by a sync that fetches nothing at all.
    """
    subject = a_subject("behind-a-redirect")
    service_wire.serve(compose_a_roster(platform_on_https, [roster_contract.member(subject)]))
    service_wire.redirecting(str(platform_on_https.address), METADATA_URL)
    service_wire.answering(
        METADATA_URL, {"id": "the-metadata-endpoint", "context": {"id": "x"}, "members": []}
    )

    sync(
        roster_sync,
        platform_on_https,
        service_wire,
        committed_rows,
        deployment_settings,
        resolve=resolving_the_platform,
    )

    assert not [call for call in service_wire.calls if call.url == METADATA_URL], (
        f"The sync followed a 302 from the roster's own address to {METADATA_URL!r}, carrying the "
        "tool's Bearer token. Every rule `refuse_invalid_fetched_address` applies was applied to "
        "the address that was *stored*, and the request ended somewhere else — which is the whole "
        f"of {roster_contract.cloud_metadata_host!r} being reachable from a validated URL."
    )
    assert not roster_rows.enrollments(), (
        "Members were ingested from a page that answered a redirect. Whatever parsed as a "
        "membership container came from the redirect's target, which is not the roster service "
        "this section is bound to."
    )
    assert roster_rows.calls_for(platform_on_https.id), (
        "A page answered 30x and the sync recorded no `nrps_call` row at all, so §6.1's console "
        "shows a section that was never called rather than one whose roster address is behind a "
        "redirect this tool will not take."
    )


# ---------------------------------------------------------------------------
# Rule 5 and the pin: the address that was judged is the address the request goes
# to. Two controls first — **a red in either means these tests are broken, not the
# sync**, because both are about this suite's own wire.
# ---------------------------------------------------------------------------


def test_the_wire_routes_a_request_by_the_host_header_when_one_is_set(
    platform_on_https: Any, service_wire: Any, roster_contract: Any
) -> None:
    """A control: this wire can represent a pinned connection at all.

    A pinned request is sent to a resolved *address* under the platform's own
    hostname, and nothing in this suite could answer one before this batch: the
    wire routed by the URL, so a request to `93.184.216.34` would have arrived at
    an unmounted host and raised. Every pin assertion below rests on this routing
    working, and "the sync fetched nothing hostile" is equally true of a wire that
    cannot answer the pinned request at all (`docs/MISTAKES.md` entry 3).

    Both directions, because a routing rule that fired for *every* request would
    be as wrong: with the header the answer is served, without it the request
    reaches an address no application is mounted at and the wire says so.
    """
    probe = f"https://{platform_on_https.host}/pinned-probe"
    service_wire.answering(probe, {"id": "answered-by-host"})
    pinned = f"https://{roster_contract.a_global_address}/pinned-probe"

    answered = service_wire.session().get(pinned, headers={"Host": platform_on_https.host})

    assert answered.json().get("id") == "answered-by-host", (
        f"A request to {pinned!r} carrying `Host: {platform_on_https.host}` was answered "
        f"{answered.status_code} / {answered.text[:120]!r}. The wire has to route it the way a "
        "server does — by the name the client stated — or a pinned sync cannot be driven here."
    )

    unrouted: BaseException | None = None
    try:
        service_wire.session().get(pinned)
    except Exception as refused:  # the wire's own RuntimeError, named below
        unrouted = refused
    assert unrouted is not None and roster_contract.a_global_address in str(unrouted), (
        f"A request to {pinned!r} with no `Host` header was answered rather than refused "
        f"({unrouted!r}). Then the routing above is not reading the header at all, and every pin "
        "assertion below would pass against a wire that ignores where the request went."
    )


def test_the_sync_takes_the_resolution_seam_this_suite_injects(roster_sync: Any) -> None:
    """The parameter this batch adds to the sync, named once so the section has a cause.

    `sync_section(session, section_id, http=None, settings=None, resolve=None)` is
    the settled signature. Without the parameter, every test below either drives
    real DNS — `roster-platform.invalid` resolves nowhere, so the whole module
    would go red on the machine rather than on the code — or drives a sync with no
    rule 5 in it at all.

    It also closes the quiet failure in `sync` above, which offers the resolver
    only when a test supplies one: a build that renamed the parameter would take
    the default resolver silently, and this is the assertion that says so instead.
    """
    import inspect

    parameters = inspect.signature(roster_sync.sync_one_section).parameters
    assert any(roster_sync.role_of(name) == "resolve" for name in parameters), (
        f"`{roster_sync.sync_one_section.__name__}` takes {sorted(parameters)} and none of them is "
        "the resolution seam. The batch threads `resolve` from `sync_section` into "
        "`refuse_invalid_fetched_address`, which is the only way a test can judge an address "
        "without a name server. `SYNC_ROLES` in tests/fixtures/roster_sync.py holds the aliases "
        "this recognises."
    )


def test_the_walk_connects_to_the_address_it_judged_and_not_to_a_later_answer(
    roster_sync: Any,
    platform_on_https: Any,
    service_wire: Any,
    compose_a_roster: Any,
    committed_rows: Any,
    roster_rows: Any,
    roster_contract: Any,
    deployment_settings: Any,
    resolving: Any,
    a_subject: Any,
) -> None:
    """The pin: a name that answers differently the second time does not move the connection.

    Judging an address and then letting the transport resolve the name again is a
    check of one thing and a request to another. The window is small and entirely
    usable: the platform's own DNS answers a public address while the walk is
    being judged and a private one while the page is being fetched, and every rule
    this module asserts has been satisfied on an address the packet never went to.
    It is the same shape as the redirect above — the address that passed the rules
    is not the address the request ends at — arriving one layer down.

    So the resolver here answers a **different, still globally routable** address
    the second time it is asked. Still routable, deliberately: if the second answer
    were private, a sync with no pin at all would refuse the second page and this
    test would pass without a pin existing (`docs/MISTAKES.md` entry 3). The only
    thing that can tell a pinned walk from an unpinned one is *which* good address
    the second GET went to.

    **The mutation this kills**: the adapter left unmounted, or mounted and
    re-resolving per request; and `pins[host]` overwritten by a later resolution
    rather than kept.

    **The `Host` header is asserted beside the address** because without it the
    pin is a downgrade: a request to an IP literal with no hostname stated
    verifies its certificate against the address, which no LMS's certificate
    names — so a pin that dropped the name would turn every real deployment's
    sync into a TLS failure, and this suite's in-process wire would never notice.
    """
    first = roster_contract.a_global_address
    later = roster_contract.another_global_address
    answers = iter([(first,), (later,)])
    resolver = resolving({platform_on_https.host: lambda: next(answers, (later,))})
    members = [a_subject("pin-page-one"), a_subject("pin-page-two")]
    service_wire.serve(
        compose_a_roster(
            platform_on_https,
            [roster_contract.member(subject) for subject in members],
            size=1,
        )
    )

    failure = sync(
        roster_sync,
        platform_on_https,
        service_wire,
        committed_rows,
        deployment_settings,
        resolve=resolver,
    )

    assert failure is None, f"A two-page walk over a pinned host raised {failure!r}."
    fetched = roster_gets(service_wire, platform_on_https)
    assert len(fetched) == 2, (
        f"The walk made {len(fetched)} roster GETs and this test needs two — the pages it made "
        f"were {[call.url for call in fetched]}. With one page there is no second resolution and "
        "nothing here is being measured."
    )
    for call in fetched:
        assert urlsplit(call.url).hostname == first, (
            f"A roster page was fetched at {call.url!r}. The first judgment resolved "
            f"{platform_on_https.host!r} to {first!r} and that is the address both requests must "
            f"go to; the resolver's second answer was {later!r}, which is what a rebind between "
            "the check and the GET looks like."
        )
        stated = (call.host_header or "").split(":")[0].lower()
        assert stated == platform_on_https.host, (
            f"A roster page was fetched at {call.url!r} stating `Host: {call.host_header!r}`. The "
            f"request has to name {platform_on_https.host!r}, so the platform serves the right "
            "virtual host and its certificate is verified against the name that was judged rather "
            "than against an address no certificate carries."
        )
    for subject in members:
        assert roster_rows.enrollments_for(subject), (
            f"{subject!r} was not ingested from a two-page roster fetched over a pinned "
            f"connection. The pages the sync fetched were {[call.url for call in fetched]}."
        )


def test_a_next_page_on_a_host_that_resolves_privately_is_refused(
    roster_sync: Any,
    platform_on_https: Any,
    service_wire: Any,
    compose_a_roster: Any,
    committed_rows: Any,
    roster_rows: Any,
    roster_contract: Any,
    deployment_settings: Any,
    resolving: Any,
    a_subject: Any,
) -> None:
    """E1-11's residual finding, driven: the hop is judged by its address, not its spelling.

    The finding this batch closes. A registered platform points `rel="next"` at an
    internal service that holds a **valid public certificate on a private
    address** — a name, over `https`, matching no literal any of the four rules
    read. Every rule passes it, TLS verifies, and the tool issues the GET with its
    NRPS Bearer token attached; the answer is parsed as roster members, so a blind
    request is still a request that reaches something.

    The contract on refusal is E1-11's own and is unchanged here: the walk stops,
    the refusal is recorded against the section's **stored** address with no
    status code, the platform-chosen URL never reaches the `nrps_call.url` column
    a console reads, and the first page's member — validly fetched — is kept.

    **The mutation this kills**: rule 5 threaded into the stored address and not
    into the walk's per-URL judgment, which passes every existing test in this
    module. **Its pair** is the next test, where the same shape of hop resolving
    to a public address walks.
    """
    hostile = f"https://{roster_contract.an_internal_host}/memberships"
    reachable = a_subject("before-the-private-hop")
    resolver = resolving(
        {
            platform_on_https.host: (roster_contract.a_global_address,),
            roster_contract.an_internal_host: (roster_contract.a_private_address,),
        }
    )
    service_wire.serve(
        compose_a_roster(
            platform_on_https,
            [roster_contract.member(reachable)],
            next_url=hostile,
        )
    )

    sync(
        roster_sync,
        platform_on_https,
        service_wire,
        committed_rows,
        deployment_settings,
        resolve=resolver,
    )

    assert not [call for call in service_wire.calls if call.url == hostile], (
        f"The sync fetched {hostile!r}, whose host resolves to "
        f"{roster_contract.a_private_address!r} — an address inside the network this worker sits "
        "in — because a platform's `Link` header named it. The tool's Bearer token went with it. "
        "Rules 1 to 4 all pass this URL: it is `https`, it is not the mock, and its host is a name "
        "rather than a refused literal."
    )
    recorded = roster_rows.calls_for(platform_on_https.id)
    assert not [row for row in recorded if row.get("url") == hostile], (
        f"An `nrps_call` row carries the platform-chosen URL {hostile!r}: "
        f"{[dict(row) for row in recorded]}. The refusal is recorded against the section's own "
        f"stored address ({str(platform_on_https.address)!r}), which is E1-11's F1-4 and is not "
        "this batch's to reopen."
    )
    refusals = [row for row in recorded if row.get("response_code") != 200]
    assert refusals, (
        f"No `nrps_call` row records the refusal — the section's rows are "
        f"{[dict(row) for row in recorded]}. §6.1's console is where an operator learns that a "
        "platform is advertising addresses this tool will not call."
    )
    assert roster_rows.enrollments_for(reachable), (
        "The first page's member was not ingested. The refusal is per URL: a walk that discarded "
        "the whole container because its second page was hostile would lose a class that synced "
        "correctly up to the boundary."
    )


def test_a_next_page_on_a_second_host_that_resolves_publicly_still_walks(
    roster_sync: Any,
    platform_on_https: Any,
    service_wire: Any,
    compose_a_roster: Any,
    committed_rows: Any,
    roster_rows: Any,
    roster_contract: Any,
    deployment_settings: Any,
    resolving: Any,
    a_subject: Any,
) -> None:
    """The pair: a platform paging onto a second host of its own is not a fault.

    A real platform may serve its roster's later pages from another name — a CDN,
    a second cluster, a tenant-specific host — and rule 5 has nothing to say about
    that as long as the addresses are public. Without this row, every refusal in
    this section is satisfied by a walk that refuses any hop off the section's own
    host, which stops paging for a perfectly ordinary deployment and which no
    refusal test would notice.

    **The mutation this kills**: rule 5 implemented as "the fetched host must equal
    the stored host", which is the cheapest way to pass every other test here.
    """
    second_host = roster_contract.a_second_platform_host
    following = f"https://{second_host}{SECOND_PAGE_PATH}"
    members = [a_subject("first-host"), a_subject("second-host")]
    resolver = resolving(
        {
            platform_on_https.host: (roster_contract.a_global_address,),
            second_host: (roster_contract.another_global_address,),
        }
    )
    service_wire.serve(
        compose_a_roster(
            platform_on_https,
            [roster_contract.member(members[0])],
            next_url=following,
        )
    )
    second_page = compose_a_roster(platform_on_https, [roster_contract.member(members[1])])
    second_page.path = SECOND_PAGE_PATH
    service_wire.serve(second_page)

    failure = sync(
        roster_sync,
        platform_on_https,
        service_wire,
        committed_rows,
        deployment_settings,
        resolve=resolver,
    )

    assert failure is None, f"A walk onto a publicly-resolving second host raised {failure!r}."
    for subject in members:
        assert roster_rows.enrollments_for(subject), (
            f"{subject!r} was not ingested. The pages the sync fetched were "
            f"{[call.url for call in service_wire.calls if call.method.upper() == 'GET']}."
        )
    hop = [call for call in service_wire.calls if call.path == SECOND_PAGE_PATH]
    assert hop, f"The second page at {following!r} was never fetched."
    stated = [(call.host_header or "").split(":")[0].lower() for call in hop]
    assert all(name == second_host for name in stated), (
        f"The hop to {following!r} stated `Host: {stated!r}`. A pinned request names the host it "
        "was judged for; this one names something else, so its certificate would be verified "
        "against the wrong name."
    )


def test_a_development_stack_fetches_its_own_roster_host_without_resolving_it(
    roster_sync: Any,
    synced_section: Any,
    service_wire: Any,
    compose_a_roster: Any,
    committed_rows: Any,
    roster_rows: Any,
    roster_contract: Any,
    development_settings: Any,
    resolving: Any,
    a_subject: Any,
) -> None:
    """The one test here under the development name, and it is the exemption's whole point.

    Everywhere else in this module runs under a deployment, because that is where
    the rules are in force. This case only exists under development: the fetched
    rules skip rule 5 for the section's own stored host, so the demo stack does
    not pay a name lookup per roster page for an address its own operator wrote —
    and, at the wire, that host is not pinned, so the request goes out under the
    name exactly as it did before this batch.

    The platform here is the ordinary `synced_section`, on the mock's own address,
    which is what a development stack really syncs.

    **The mutation this kills**: rule 5 applied to every fetched URL regardless of
    environment, which would resolve a Compose service name on every page of every
    hourly walk; and a `PinnedResolutionAdapter` that rewrites a host it never
    pinned, which would send the request to an address nothing judged.

    **A red here means the exemption is not in place — or that the pin is
    rewriting hosts it holds no pin for.**
    """
    resolver = resolving({})
    subject = a_subject("development-exempt")
    service_wire.serve(compose_a_roster(synced_section, [roster_contract.member(subject)]))

    failure = sync(
        roster_sync,
        synced_section,
        service_wire,
        committed_rows,
        development_settings,
        resolve=resolver,
    )

    assert failure is None, f"A development stack's own roster sync raised {failure!r}."
    assert not resolver.asked, (
        f"The sync resolved {resolver.asked!r} while fetching the section's own stored roster "
        "address on a development stack. That address is the operator's own, the exemption is "
        "written for it, and the hourly walk pays the lookup once per page of every section."
    )
    fetched = roster_gets(service_wire, synced_section)
    assert fetched, "The development stack's roster was never fetched at all."
    for call in fetched:
        assert urlsplit(call.url).hostname == synced_section.host, (
            f"A roster page was fetched at {call.url!r} rather than at "
            f"{synced_section.host!r}. Nothing resolved this host, so nothing pinned it, and a "
            "rewritten URL here is the adapter sending a request to an address no rule judged."
        )
    assert roster_rows.enrollments_for(subject), (
        "The development stack's roster member was not ingested, so whatever this asserts about "
        "resolution is being asserted about a walk that did not happen."
    )


def test_a_development_stack_refuses_a_hop_off_its_own_host_that_resolves_privately(
    roster_sync: Any,
    synced_section: Any,
    service_wire: Any,
    compose_a_roster: Any,
    committed_rows: Any,
    roster_rows: Any,
    roster_contract: Any,
    development_settings: Any,
    resolving: Any,
    a_subject: Any,
) -> None:
    """The other half of the exemption: what a development stack still judges.

    The test above proves a development stack does **not** resolve its own stored
    roster host. On its own that is only half a statement, and the missing half is
    the one the exemption exists to protect: everywhere the platform points the
    walk *other* than that host is judged, in development exactly as in a
    deployment. Without this, "the exemption works" is satisfied by a development
    stack that judges nothing at all — which is the whole of rule 5 switched off
    on every developer's machine and in every `make seed` demo, with the mock
    platform free to page the walk into anything the host can route to.

    **The mutation this kills**: `development_exempt_host=exempt_host` at the
    sync's per-URL judgment mutated to `development_exempt_host=None`. Under the
    settled design that argument is what *turns rule 5 on* in development — with
    `None` the rules are off there entirely — so the mutation does not weaken the
    exemption, it removes the judgment. It survives every other test in this
    module: the deployment-side tests ignore the argument (rule 5 fires there
    regardless of it), and the development test above only ever asserts that
    something was **not** resolved, which is even more true when nothing is.

    A refusal test whose subject is an argument that switches judging on cannot
    rest on the refusal alone (`docs/MISTAKES.md` entry 3): a walk that fetched
    nothing hostile because it never got that far reads identically. So the
    resolver is required to have been **asked about the hostile host** — that is
    the fingerprint of rule 5 running, and it is exactly what the mutation
    removes.

    The refusal contract is the deployment-side test's, unchanged and asserted
    again here because it is a different code path reaching it: the walk stops,
    the row is recorded against the section's **stored** address with a NULL
    `response_code` (ADR 0096, which fixes both), the platform-chosen URL never
    reaches the `nrps_call.url` column a console reads, and the first page's
    member is kept.

    The hop is spelled `https` deliberately. Were the environment misread as a
    deployment, the mock's own cleartext stored address would be refused at the
    *first* page and the ingestion assertion at the foot of this test would say so
    — so this cannot quietly become a deployment test.
    """
    hostile = f"https://{roster_contract.an_internal_host}/memberships"
    reachable = a_subject("before-the-development-hop")
    # The stored host is deliberately absent from the stub: it is the exempt one,
    # nothing may resolve it, and a lookup would raise rather than be answered.
    resolver = resolving({roster_contract.an_internal_host: (roster_contract.a_private_address,)})
    service_wire.serve(
        compose_a_roster(
            synced_section,
            [roster_contract.member(reachable)],
            next_url=hostile,
        )
    )

    sync(
        roster_sync,
        synced_section,
        service_wire,
        committed_rows,
        development_settings,
        resolve=resolver,
    )

    assert not [call for call in service_wire.calls if call.url == hostile], (
        f"A development stack fetched {hostile!r}, whose host resolves to "
        f"{roster_contract.a_private_address!r}, because the platform's `Link` header named it. "
        "The exemption is for the section's own stored address and for nothing else; a hop off it "
        "is a URL the platform chose, and the tool's Bearer token goes with the request."
    )
    asked = [host.lower().rstrip(".") for host in resolver.asked]
    assert roster_contract.an_internal_host in asked, (
        f"The sync resolved {resolver.asked!r} and never asked about "
        f"{roster_contract.an_internal_host!r}. Then rule 5 did not run for the hop at all, and "
        "whatever stopped the walk was not the address being judged — which is precisely what "
        "passing `development_exempt_host=None` at the judgment looks like from the outside."
    )
    recorded = roster_rows.calls_for(synced_section.id)
    assert not [row for row in recorded if row.get("url") == hostile], (
        f"An `nrps_call` row carries the platform-chosen URL {hostile!r}: "
        f"{[dict(row) for row in recorded]}. ADR 0096 records the refusal against the section's "
        f"own stored address ({str(synced_section.address)!r}), because a row keyed to the "
        "platform's string puts a value somebody else supplied onto §6.1's console."
    )
    refusals = [row for row in recorded if row.get("response_code") is None]
    assert refusals, (
        f"No `nrps_call` row records the refusal with a NULL `response_code` — the section's rows "
        f"are {[dict(row) for row in recorded]}. ADR 0096: the refused page is a call the tool "
        "decided not to make, and an operator reading the console learns that from the row."
    )
    assert all(row.get("url") == str(synced_section.address) for row in refusals), (
        f"A refusal row is keyed to something other than the section's stored address "
        f"({str(synced_section.address)!r}): {[dict(row) for row in refusals]}."
    )
    assert roster_rows.enrollments_for(reachable), (
        "The first page's member was not ingested. The refusal is per URL — a partial walk keeps "
        "the pages that were validly fetched — and on a development stack this is also the "
        "assertion that says the sync got past its own stored address, which it could not have "
        "done under a deployment's rules."
    )


def test_a_development_stack_walks_a_hop_off_its_own_host_that_resolves_publicly(
    roster_sync: Any,
    synced_section: Any,
    service_wire: Any,
    compose_a_roster: Any,
    committed_rows: Any,
    roster_rows: Any,
    roster_contract: Any,
    development_settings: Any,
    resolving: Any,
    a_subject: Any,
) -> None:
    """The pair, in development, and no existing test holds it.

    `test_a_next_page_on_a_second_host_that_resolves_publicly_still_walks` asks
    this question under a deployment, where the exempt host argument is ignored;
    nothing asked it under the development name, which is the only environment
    where that argument decides anything. Without this row, the refusal above is
    satisfied by a development stack that refuses **every** host that is not its
    own stored one — a walk that judges nothing and refuses everything reads the
    same from a single refusal test, and it would stop pagination dead on the demo
    stack the moment a platform paged onto a second name.

    So: same environment, same shape of hop, same stub with one value different —
    the second host resolves to a globally routable address — and the walk has to
    reach the member on the second page.
    """
    second_host = roster_contract.a_second_platform_host
    following = f"https://{second_host}{SECOND_PAGE_PATH}"
    members = [a_subject("development-first-host"), a_subject("development-second-host")]
    resolver = resolving({second_host: (roster_contract.another_global_address,)})
    service_wire.serve(
        compose_a_roster(
            synced_section,
            [roster_contract.member(members[0])],
            next_url=following,
        )
    )
    second_page = compose_a_roster(synced_section, [roster_contract.member(members[1])])
    second_page.path = SECOND_PAGE_PATH
    service_wire.serve(second_page)

    failure = sync(
        roster_sync,
        synced_section,
        service_wire,
        committed_rows,
        development_settings,
        resolve=resolver,
    )

    assert (
        failure is None
    ), f"A development stack walking onto a publicly-resolving second host raised {failure!r}."
    for subject in members:
        assert roster_rows.enrollments_for(subject), (
            f"{subject!r} was not ingested on a development stack. The pages the sync fetched were "
            f"{[call.url for call in service_wire.calls if call.method.upper() == 'GET']}."
        )
    asked = [host.lower().rstrip(".") for host in resolver.asked]
    assert second_host in asked, (
        f"The sync resolved {resolver.asked!r} and never asked about {second_host!r}, so this walk "
        "went through without rule 5 seeing the hop — the acceptance is then not the pair to the "
        "refusal above, because nothing judged the address either time."
    )
