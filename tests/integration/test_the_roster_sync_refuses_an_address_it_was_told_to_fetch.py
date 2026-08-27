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
"""

from typing import Any

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.lti]

# Where a hostile `Link` header points. Built as absolute URLs on hosts ADR 0081
# names, because that is what a header carries; the path is arbitrary and the host
# is the whole subject.
METADATA_URL = "http://169.254.169.254/latest/meta-data/iam/security-credentials/"
LOOPBACK_URL = "http://127.0.0.1:9/memberships"


@pytest.fixture
def platform_on_https(roster_platforms: Any, roster_contract: Any) -> Any:
    """One registered platform whose advertised addresses pass rule 1 under a deployment."""
    return roster_platforms(roster_contract.https_platform_issuer)


def sync(
    roster_sync: Any, section: Any, wire: Any, rows: Any, settings: Any
) -> BaseException | None:
    """Run one section's sync, answering the exception it raised or `None`.

    Whether the sync raises or returns on a refusal is deliberately not asserted
    anywhere in this module: ADR 0090's consequences leave that to the writer — "a
    later sanctioned writer running on a job rather than on a request may
    reasonably want the opposite: fail loudly, let the task retry". What is
    asserted is the row it leaves and the rows it does not write, which is the same
    contract the token-refusal test next door holds.
    """
    try:
        roster_sync.call(
            roster_sync.sync_one_section,
            session=rows.session,
            section_id=section.id,
            http=wire.session(),
            settings=settings,
        )
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

    sync(roster_sync, platform_on_https, service_wire, committed_rows, deployment_settings)

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
        "*Which* code a refusal carries is deliberately not asserted: the fix settles that it is "
        "recorded as a refusal rather than as D9's transport NULL and leaves the sentinel to the "
        "implementer."
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
        roster_sync, platform_on_https, service_wire, committed_rows, deployment_settings
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

    sync(roster_sync, platform_on_https, service_wire, committed_rows, deployment_settings)

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
