"""The walk follows `rel="next"` as the platform wrote it — the boundary review's H1.

`docs/tickets/e1/boundary-review.md`: "`pylti1p3` 2.0.0 (`service_connector.py:129`)
extracts that URL from a lowercased copy of the `Link` header. RFC 3986 makes path
and query case-sensitive; a repro showed `?page=Bookmark:QUJDeHl6` coming back as
`?page=bookmark:qujdehl6`." And the sibling the same finding records: "a `Link`
header carrying another parameter before `rel="next"` (`<url>; title="x";
rel="next"`) misses the regex entirely, ending the walk early as complete — a
silently truncated roster with no error recorded."

`boundary-fix-plan.md`, batch A item 1, is what this module asserts: "The walk
follows the `rel="next"` URL exactly as the platform sent it — case preserved — and
recognizes the link whatever else the `Link` header carries: other parameters
before or after `rel`, unquoted `rel=next`, multiple links in one header. A page
whose header has no next link ends the walk complete; a next URL that cannot be
fetched still ends it incomplete."

**Why this is invisible to every other test in the suite.** E0-15's mock pages its
container with a decimal cursor on a lower-case path (`?page=2`), so
`test_a_multipage_roster_ingests_the_member_only_the_last_page_holds` is green
against a client that lowercases every URL it is handed. Canvas's cursor is a
base64 bookmark and its case is load-bearing. So the second page here is served at
a path and under a query that carry capitals, and the assertion is on the URL the
client *sent* — read off `service_wire`, which records each request as it left the
client, rather than on whether some page came back.

**How the second page is served, and why that is not the fixture's job.**
`compose_a_roster` builds the container and `ServiceWire.serve` answers it at its
own path; neither can carry a `Link` header of this module's choosing, because
every header the fixture writes is the one shape a conformant platform sends. The
two helpers below are that one difference and nothing else: `HeaderRewritten` swaps
the `Link` header on a page the fixture composed — its value *and* the case of its
name — and `served_at` moves a composed page to a path of its own. Both are here
rather than in `tests/fixtures/` because no other module needs them — the fixture
module's own docstring draws that line.

**What the fix round added, and why each one needed a test that did not exist.**
The verification battery killed 15 mutations on the tests above and found four
survivors; the four are the subject of the second half of this module.

  - **"Incomplete" was a word rather than an assertion.** Mutating the failure
    branch to report the walk as *complete* survived every test in the tree: a
    truncated walk that claims completeness makes the sync close every member it
    did not see, so a platform whose second page fails for an hour ends the
    enrollment of everyone on it. So the failed walk is now asserted to close
    nobody, and the pair — a walk that really is complete and really has lost a
    member closes them — is
    `test_the_roster_sync_records_enrollment_windows.py::test_a_member_who_vanishes_
    from_the_roster_is_ended_at_the_syncs_own_date`, cited rather than copied.
  - **Every failure here arrived as an HTTP status**, so the handler for a
    transport that never answers at all was unasserted. One test now fails the
    second page at the socket rather than at the status line.
  - **The header's *name* was only ever served lower case** by this module's own
    machinery, so a reader narrowed to exactly `link` passed — `docs/MISTAKES.md`
    entry 30's shape, where the fixture supplies the value under test. RFC 9110
    §5.1 makes a field name case-insensitive and RFC 8288 §3 spells this one
    `Link`; both spellings are now served.
  - **The parser is not quoted-string aware in either direction.** A legal comma
    inside a quoted parameter value ends the link early, and a `rel=next` written
    inside a quoted value is followed as though the platform had declared it. The
    first is the same silent truncation as H1 itself, reached through a spelling
    RFC 8288 explicitly permits; the second is a platform-controlled string
    choosing where this tool sends its Bearer token.

**One vector this module drives is a security finding rather than a paging one.**
A URL whose authority carries a raw backslash is parsed one way by `urlsplit` and
another by `requests`, so the address that is judged is not the address that is
dialled. That belongs with the other address rules and is asserted in
`test_the_roster_sync_refuses_an_address_it_was_told_to_fetch.py` and in
`tests/unit/test_registration_address_constraints.py`, not here.

**The controls come first and they must be green.** A header this module believes
declares `rel="next"` at a URL, and a wire that can tell that URL from its
lower-cased spelling, are what every assertion below rests on. **A red in the
control section means these tests are broken, not the sync.**

**What the sync does with a failure is deliberately not asserted**, the same
boundary `test_the_roster_sync_refuses_an_address_it_was_told_to_fetch.py` keeps:
ADR 0090's consequences leave raise-or-return to the writer, so `sync` below hands
back the exception instead of asserting about it, and what is asserted is the rows
that were written and the requests that were made.
"""

from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.lti]

# `roster_sync`, `synced_section`, `service_wire`, `compose_a_roster`,
# `roster_contract`, `roster_rows` and `a_subject` come from
# `tests/fixtures/roster_sync.py`, and `link_relations_in` from
# `tests/fixtures/lti_services.py`. Reached as fixtures rather than imported, for
# the reason every module in this suite gives: an import of a fixtures module by
# name depends on where pytest put `tests/` on `sys.path`, and an import error is
# not a red.

# Where the second page lives when the question is *recognition* — all lower case,
# so that the only variable in those tests is the shape of the `Link` header.
NEXT_PAGE_PATH = "/rosters/e1-boundary-next-page"

# Where it lives when the question is *case*. Capitals in the path and capitals in
# the query, because RFC 3986 §6.2.2.1 makes both case-sensitive and the finding's
# own repro is a query: `?page=Bookmark:QUJDeHl6` came back `?page=bookmark:qujdehl6`.
# The value is Canvas's shape — a base64 bookmark behind a `Bookmark:` prefix —
# transcribed from the finding rather than invented, so a green here is about the
# platform this breaks against.
CASE_CARRYING_PAGE_PATH = "/rosters/E1-Boundary-Next-Page"
CASE_CARRYING_QUERY = "page=Bookmark:QUJDeHl6"

# A page no header ever declares as `next`, served all the same. It is what turns
# "the walk stopped" into an assertion rather than an absence: a client that
# follows the first `<...>` in a header regardless of its relation reaches this
# page, and a client that reads `rel` reaches it never. Nothing but a `rel="prev"`
# or a `rel="first"` ever points here.
DECOY_PAGE_PATH = "/rosters/e1-boundary-not-the-next-page"

# The `Link` headers a platform may send, each declaring `next` at the same URL.
# RFC 8288 §3 makes every one of these legal: the parameters of a link are
# unordered, `rel` is one of them rather than the first, its value is a token that
# may be quoted or bare, and a header may carry several comma-separated links.
# `quoted-rel-only` is the shape the mock sends and is here as the instrument's own
# check — if that one fails, the machinery is wrong rather than the sync.
LINK_HEADER_SHAPES = {
    "quoted-rel-only": '<{url}>; rel="next"',
    "a-parameter-before-rel": '<{url}>; title="Page two of the container"; rel="next"',
    "a-parameter-after-rel": '<{url}>; rel="next"; type="application/json"',
    "an-unquoted-rel": "<{url}>; rel=next",
    "three-links-in-one-header": (
        '<{decoy}>; rel="prev", <{url}>; rel="next", <{decoy}>; rel="first"'
    ),
}

# How a platform may spell the header's *name*. RFC 9110 §5.1: "Field names are
# case-insensitive"; RFC 8288 §3 writes this one `Link`, which is the spelling
# Canvas and Moodle both send and the one this module's own machinery never sent
# until the fix round — so a reader narrowed to exactly `link` passed every test
# here (`docs/MISTAKES.md` entry 30: the fixture supplied the value under test).
# `link` stays in the set as the instrument's own case.
LINK_HEADER_NAMES = ("Link", "LiNk", "link")

# A parameter value carrying a comma, quoted, which RFC 8288 §3 and RFC 9110 §5.6.4
# permit: inside a quoted-string a comma is a character and not the separator
# between two links. A parser that splits the header on commas first sees this link
# end in the middle of its own title, and the `rel="next"` that follows belongs to
# nothing.
A_QUOTED_COMMA_TITLE = "Page 2, of 9"

# A `rel=next` written inside a quoted parameter value on a link the platform
# declared `prev`. A parser that searches the raw header for the relation finds
# this one, and the platform's own declaration is overruled by a string the
# platform put inside quotation marks — which is a platform choosing where this
# tool sends its Bearer token.
A_QUOTED_RELATION_TITLE = "a; rel=next"


def page_url(section: Any, path: str, query: str = "") -> str:
    """A URL on the section's own platform, at `path`, carrying `query`.

    The platform's own host throughout, so nothing in this module is about ADR
    0081's fetched-address rules: those judge a hop that leaves the section's
    stored host, and `test_the_roster_sync_refuses_an_address_it_was_told_to_fetch
    .py` is where that is the subject. Here the only thing under test is which
    string the walk fetches.
    """
    split = urlsplit(section.address or "")
    return urlunsplit((split.scheme, split.netloc, path, query, ""))


class HeaderRewritten:
    """A page the fixture composed, served under a `Link` header this test wrote.

    `ServiceWire.serve` asks a page for two things — its `path`, to file it under,
    and `document(url)`, for the body and headers to answer with — so this wraps a
    `compose_a_roster` page and rewrites exactly one header. Everything else about
    the answer stays the fixture's: the media type, the container's `context`, and
    the members.

    It is used only where the header's *shape* is the subject. Where it is not —
    the byte-exact URL, and the page that cannot be fetched — the first page is
    composed with `compose_a_roster(..., next_url=…)`, so the header those walks
    read is the fixture's own and nothing about them rests on this class.

    **`name` is the case the header's own name is served under**, and it defaults
    to the fixture's lower-case spelling so that nothing above changes. It exists
    because this class wrote `link` and only `link`, which made a reader narrowed
    to exactly that spelling pass every test in this module while a platform
    sending RFC 8288's own `Link` was ignored: the fixture was supplying the value
    under test (`docs/MISTAKES.md` entry 30).
    """

    def __init__(self, page: Any, link: str | None, name: str = "link") -> None:
        self.page = page
        self.path = page.path
        self.link = link
        self.name = name

    def document(self, url: str) -> tuple[dict[str, Any], dict[str, str]]:
        body, headers = self.page.document(url)
        served = {name: value for name, value in headers.items() if name.lower() != "link"}
        if self.link is not None:
            served[self.name] = self.link
        return body, served


def served_at(page: Any, path: str) -> Any:
    """Move a composed page to a path of its own, and hand it back.

    A second page has to live somewhere the first does not: `ServiceWire` files a
    roster by path, so two pages at one path are one page. The composed roster
    takes its path from the section's stored address, and this is the one line that
    changes it.
    """
    page.path = path
    return page


def sync(
    roster_sync: Any, section: Any, wire: Any, rows: Any, http: Any = None
) -> tuple[list[Any], Any]:
    """Run one section's sync; answer the calls it made and the exception it raised.

    The calls are sliced from the mark taken before the run, so a request this test
    made itself — a control fetching a page directly — is not counted as one the
    sync made. Whether the sync raises or returns on a failure is deliberately not
    asserted anywhere in this module (ADR 0090's consequences leave it to the
    writer); what is asserted is what it fetched and what it wrote.

    `http` is the wire's own session unless a test hands one over. One test does:
    the transport-failure case mounts an adapter that fails at the socket rather
    than at the status line, which is a failure the wire cannot express — every
    answer it gives is a well-formed HTTP response.
    """
    mark = len(wire.calls)
    try:
        roster_sync.call(
            roster_sync.sync_one_section,
            session=rows.session,
            section_id=section.id,
            http=wire.session() if http is None else http,
        )
        rows.commit()
        return wire.calls[mark:], None
    except Exception as raised:
        rows.session.rollback()
        return wire.calls[mark:], raised


def gets(calls: list[Any]) -> list[str]:
    """Every URL the client asked for with a GET, in order, as it sent them."""
    return [call.url for call in calls if call.method.upper() == "GET"]


class RefusedByTheNetwork:
    """A transport that fails the way a socket does: no answer, no status line.

    `ServiceWire` answers every request with a well-formed HTTP response, so a
    failure it produces always arrives as a status code. That left the sync's
    transport handler — the `requests.RequestException` branch — unasserted, and
    reverting it to discarding the whole container survived the battery.

    This is mounted on the session for one URL prefix, so the first page still goes
    over the wire and the second page meets a connection that is refused.
    `requests.exceptions.ConnectionError` is what a refused connection, a DNS
    failure and a reset all arrive as, so this is the class of failure rather than
    one member of it.
    """

    def __init__(self) -> None:
        self.attempts: list[str] = []

    def send(self, request: Any, **_: Any) -> Any:
        import requests

        self.attempts.append(str(request.url))
        raise requests.exceptions.ConnectionError(
            "the roster page's host refused the connection", request=request
        )

    def close(self) -> None:
        return None


def a_session_that_cannot_reach(wire: Any, url: str) -> tuple[Any, RefusedByTheNetwork]:
    """The wire's session, with `url` unreachable at the socket.

    `Session.mount` matches the longest prefix, so the page mounted here is the
    only request that fails: the token endpoint and the first page still travel
    over the wire and are recorded on it.
    """
    session = wire.session()
    adapter = RefusedByTheNetwork()
    session.mount(url, adapter)
    return session, adapter


def weeks_ago(weeks: int) -> datetime:
    """An aware instant in the past, for a member Pulse synced before today."""
    return datetime.now(UTC) - timedelta(weeks=weeks)


def one_enrollment(rows: Any, subject: str) -> Any:
    """The single enrollment row for one member, or a failure counting them."""
    found = rows.enrollments_for(subject)
    assert len(found) == 1, (
        f"The member {subject!r} has {len(found)} enrollment rows and this test is about one: "
        f"{[dict(row) for row in found]}."
    )
    return found[0]


# ---------------------------------------------------------------------------
# Controls. **A red here means these tests are broken, not the sync.**
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("shape", sorted(LINK_HEADER_SHAPES))
def test_each_link_header_shape_declares_the_next_relation_this_module_claims(
    synced_section: Any,
    service_wire: Any,
    compose_a_roster: Any,
    roster_contract: Any,
    a_subject: Any,
    link_relations_in: Any,
    shape: str,
) -> None:
    """Every header below is read by E0-15's parser and required to name the next URL.

    The tests that follow say "the walk did not fetch the next page". That
    sentence is equally true of a header which never declared one — a typo in a
    template here would report a sync that pages perfectly as broken, and a
    template that declared `next` at the *wrong* URL would report a working one as
    fixed. So each shape is served, fetched, and its header read with
    `link_relations`, the same function `MockPlatform.membership_pages` walks with
    (`docs/MISTAKES.md` entry 3: run the pattern against the text you claim it
    catches).

    The decoy is required *not* to be the `next` relation in the same breath,
    because the multi-link shape declares it as `prev` and `first` and the
    assertions below turn on the walk never going there.

    **A red here means these tests are broken, not the sync.**
    """
    following = page_url(synced_section, NEXT_PAGE_PATH)
    decoy = page_url(synced_section, DECOY_PAGE_PATH)
    header = LINK_HEADER_SHAPES[shape].format(url=following, decoy=decoy)
    service_wire.serve(
        HeaderRewritten(
            compose_a_roster(synced_section, [roster_contract.member(a_subject("first-page"))]),
            header,
        )
    )

    answered = service_wire.session().get(str(synced_section.address))

    assert answered.status_code == 200, (
        f"The composed first page answered {answered.status_code} at the section's own stored "
        f"address {synced_section.address!r}, so there is no page for a `Link` header to be "
        f"attached to. Body begins {answered.text[:200]!r}."
    )
    relations = link_relations_in(answered.headers.get("link"))
    assert relations.get("next") == following, (
        f"The `{shape}` header {header!r} declares `next` as {relations.get('next')!r} and this "
        f"module needs {following!r}. Every assertion in this file about a walk following — or not "
        "following — that relation would be about a header that never declared it."
    )
    assert relations.get("next") != decoy, (
        f"The `{shape}` header declares `next` at the decoy page {decoy!r}. That page exists to be "
        "advertised under every relation except `next`, so a walk that reached it would be right "
        "rather than wrong and the denials below would be inverted."
    )


def test_the_wire_tells_the_next_pages_own_spelling_from_a_lower_cased_one(
    synced_section: Any,
    service_wire: Any,
    compose_a_roster: Any,
    roster_contract: Any,
    a_subject: Any,
) -> None:
    """The instrument that sees H1 at all: two spellings of one URL, answered differently.

    H1 is a client that lower-cases a URL before it fetches it. A harness whose
    second page answered to either spelling could not see that happen — the walk
    would come back with the page, the member would be ingested, and the test would
    report a corrupted URL as a working walk (`docs/MISTAKES.md` entry 3).

    Three things are required here, and each is a way the instrument could be
    blind. The byte-exact URL is answered by the second page. The lower-cased
    spelling is **not** — nothing is mounted at that path, so it reaches the mock
    and comes back without this page's member. And `requests` is required to leave
    the URL alone on the way out: the recorded request carries the capitals and the
    colon exactly as they were written, so a later assertion comparing the two is
    comparing what the client sent rather than what a transport re-encoded.

    **A red here means these tests are broken, not the sync.**
    """
    following = page_url(synced_section, CASE_CARRYING_PAGE_PATH, CASE_CARRYING_QUERY)
    lowered = following.lower()
    assert lowered != following, (
        f"{following!r} is unchanged by lower-casing, so the two spellings this module tells apart "
        "are one spelling and every case assertion below is vacuous."
    )
    member = a_subject("second-page")
    service_wire.serve(
        served_at(
            compose_a_roster(synced_section, [roster_contract.member(member)]),
            CASE_CARRYING_PAGE_PATH,
        )
    )
    session = service_wire.session()
    token = synced_section.platform.nrps_token()

    exact = session.get(following, headers={"authorization": f"Bearer {token}"})

    assert exact.status_code == 200 and member in exact.text, (
        f"A GET for {following!r} answered {exact.status_code} and a body that does not carry "
        f"{member!r}: {exact.text[:200]!r}. That page is what the walk is required to reach, so "
        "with it unreachable every assertion below fails for a reason that is this module's."
    )
    assert service_wire.calls[-1].url == following, (
        f"The wire recorded the request as {service_wire.calls[-1].url!r} and it was sent as "
        f"{following!r}. `requests` has re-spelled the URL between this test and the record, so "
        "the byte-exact comparison this module makes would be a comparison against the "
        "transport's spelling rather than against the platform's."
    )

    corrupted = session.get(lowered, headers={"authorization": f"Bearer {token}"})

    assert member not in corrupted.text, (
        f"A GET for the lower-cased spelling {lowered!r} answered {corrupted.status_code} with a "
        f"body carrying {member!r}. This wire answers both spellings of the page, so a client that "
        "lower-cases the URL it was handed still gets the container — which is precisely the "
        "corruption H1 is about, made invisible."
    )


# ---------------------------------------------------------------------------
# H1 — the URL as the platform wrote it.
# ---------------------------------------------------------------------------


def test_the_walk_fetches_the_next_page_url_byte_exactly_as_the_platform_sent_it(
    roster_sync: Any,
    synced_section: Any,
    service_wire: Any,
    compose_a_roster: Any,
    committed_rows: Any,
    roster_rows: Any,
    roster_contract: Any,
    a_subject: Any,
) -> None:
    """H1's first half: the `rel="next"` URL is fetched with its case intact.

    **The mutation this kills**: extracting the next URL from a lower-cased copy of
    the `Link` header, which is what `pylti1p3` 2.0.0 does at
    `service_connector.py:129` and what this walk inherits today. The finding's own
    repro is this test's second page: `?page=Bookmark:QUJDeHl6` fetched as
    `?page=bookmark:qujdehl6`. Canvas answers the first and 404s the second, so the
    roster stops at page one and the section syncs short with nothing recorded as
    wrong.

    **The near miss it is written around**: a fix that lower-cases only the *host*
    is correct and passes — RFC 3986 §6.2.2.1 makes scheme and host
    case-insensitive and path and query case-sensitive, and the assertion compares
    the URL the walk sent against the URL the platform sent, which agree on the
    host in either spelling because the fixture writes the host in lower case.

    Two assertions, and neither is enough alone. The URL, because a walk that
    fetched the right container by luck — a case-insensitive server, a retry, a
    second guess — would still be a client that corrupts what a platform hands it.
    And the member, because a client can send exactly the right string and throw
    the answer away.
    """
    first = a_subject("first-page")
    second = a_subject("second-page")
    following = page_url(synced_section, CASE_CARRYING_PAGE_PATH, CASE_CARRYING_QUERY)
    # The fixture's own `rel="next"` header, not this module's: the shape of the
    # header is not what this test varies, and `compose_a_roster(..., next_url=…)`
    # is the seam the security round built for a first page that advertises an
    # address of the caller's choosing.
    service_wire.serve(
        compose_a_roster(synced_section, [roster_contract.member(first)], next_url=following)
    )
    service_wire.serve(
        served_at(
            compose_a_roster(synced_section, [roster_contract.member(second)]),
            CASE_CARRYING_PAGE_PATH,
        )
    )

    during, _ = sync(roster_sync, synced_section, service_wire, committed_rows)

    fetched = gets(during)
    assert following in fetched, (
        f"The platform advertised its next page as {following!r} and the walk fetched {fetched}. "
        f"The lower-cased spelling {following.lower()!r} is the one `pylti1p3` extracts, from a "
        "lower-cased copy of the whole `Link` header — RFC 3986 makes path and query "
        "case-sensitive, so a platform whose cursor carries capitals (Canvas's base64 bookmark) "
        "answers 404 and the roster ends silently at page one."
    )
    assert roster_rows.enrollments_for(second), (
        f"The second page's member {second!r} has no enrollment. The walk sent the platform's own "
        "URL and did not ingest what came back, so the container's later pages are fetched and "
        "dropped — a class that syncs short, and short reads as small."
    )


@pytest.mark.parametrize("shape", sorted(LINK_HEADER_SHAPES))
def test_the_walk_follows_the_next_relation_whatever_else_the_link_header_carries(
    roster_sync: Any,
    synced_section: Any,
    service_wire: Any,
    compose_a_roster: Any,
    committed_rows: Any,
    roster_rows: Any,
    roster_contract: Any,
    a_subject: Any,
    shape: str,
) -> None:
    """H1's second half: `rel="next"` is found wherever RFC 8288 permits it to sit.

    **The mutation this kills**: reading the relation with a pattern anchored to one
    spelling — `<([^>]*)>;\\s*rel="next"` against the whole header, which is the
    library's, and which misses `<url>; title="x"; rel="next"` entirely. The
    boundary review found that shape by verification and called it the worse
    sibling of the case bug: "ending the walk early as complete — a silently
    truncated roster with no error recorded". Nothing else in this suite sends a
    header the mock does not, so nothing else can see it.

    **The near misses, each a parameter of this test.** A parameter before `rel` and
    a parameter after it are different failures of the same pattern. An unquoted
    `rel=next` is RFC 8288 §3's bare token, which a quote-requiring pattern misses
    and which some platforms send. Several links in one header is what a platform
    sends when it offers `prev`, `next` and `first` together, and it is where a
    pattern that takes the *first* `<...>` in the header goes wrong.

    **And the near miss in the other direction, asserted in every case**: the decoy
    page is served and is advertised as `prev` and `first` and never as `next`. A
    walk loosened until it follows any link at all reaches it, so "the next page
    arrived" cannot be bought by fetching everything the header names.

    `quoted-rel-only` is the shape E0-15's mock sends and is expected to pass
    before the fix as well as after; it is the parameter that says the machinery
    can express a working walk at all.
    """
    first = a_subject("first-page")
    second = a_subject("second-page")
    decoyed = a_subject("decoy-page")
    following = page_url(synced_section, NEXT_PAGE_PATH)
    decoy = page_url(synced_section, DECOY_PAGE_PATH)
    service_wire.serve(
        HeaderRewritten(
            compose_a_roster(synced_section, [roster_contract.member(first)]),
            LINK_HEADER_SHAPES[shape].format(url=following, decoy=decoy),
        )
    )
    service_wire.serve(
        served_at(
            compose_a_roster(synced_section, [roster_contract.member(second)]), NEXT_PAGE_PATH
        )
    )
    service_wire.serve(
        served_at(
            compose_a_roster(synced_section, [roster_contract.member(decoyed)]), DECOY_PAGE_PATH
        )
    )

    during, _ = sync(roster_sync, synced_section, service_wire, committed_rows)

    assert following in gets(during), (
        f"With the next page advertised by a `{shape}` header, the walk fetched {gets(during)} and "
        f"never {following!r}. RFC 8288 §3 makes that header a link with unordered parameters, so "
        "a platform is free to send it and this tool is not free to miss it — the walk ends early, "
        "reports nothing, and the section's roster is quietly short."
    )
    assert roster_rows.enrollments_for(second), (
        f"The next page's member {second!r} has no enrollment, from a `{shape}` header. Fetching "
        "the page and dropping what it answered is the same short roster by another route."
    )
    assert not roster_rows.enrollments_for(decoyed), (
        f"The member {decoyed!r} was ingested from the decoy page, which this header advertises "
        "only as `prev` and `first`. A walk that follows whatever URL a `Link` header carries "
        "passes every other assertion here and re-reads the container's earlier pages for ever."
    )


def test_a_first_page_whose_header_offers_no_next_relation_ends_the_walk_complete(
    roster_sync: Any,
    synced_section: Any,
    service_wire: Any,
    compose_a_roster: Any,
    committed_rows: Any,
    roster_rows: Any,
    roster_contract: Any,
    a_subject: Any,
) -> None:
    """The accepted half's pair: a container that ends, ending cleanly.

    "A page whose header has no next link ends the walk complete." Without this,
    every assertion in this module is satisfied by a walk that fetches everything a
    header mentions and never stops — which is the shape a loosened `rel` match
    produces, and which turns one hourly sync into an endless one.

    The header here is not absent: it declares `prev` at a page that *is* served,
    which is the state a real platform's last page is in. So the walk has somewhere
    to go and a reason not to.

    **The mutations this kills**: a relation match loose enough to read `rel="prev"`
    as a next page, and a walk that follows the first `<...>` in any header it is
    given. Both leave the decoy's member in the database and a second GET on the
    wire.

    Complete rather than merely finished: one call row, carrying 200. D9 gives a
    NULL `response_code` one meaning — a call that never reached the platform — so
    a container that ended normally and left a row saying otherwise reads on §6.1's
    console as a section whose sync is failing every hour.
    """
    first = a_subject("first-page")
    decoyed = a_subject("decoy-page")
    decoy = page_url(synced_section, DECOY_PAGE_PATH)
    service_wire.serve(
        HeaderRewritten(
            compose_a_roster(synced_section, [roster_contract.member(first)]),
            f'<{decoy}>; rel="prev"',
        )
    )
    service_wire.serve(
        served_at(
            compose_a_roster(synced_section, [roster_contract.member(decoyed)]), DECOY_PAGE_PATH
        )
    )

    during, _ = sync(roster_sync, synced_section, service_wire, committed_rows)

    assert decoy not in gets(during), (
        f"The walk fetched {decoy!r}, which the first page's header declares as `prev`. A client "
        "that reads any link as the next page walks a container backwards and never reaches its "
        f"end. It fetched {gets(during)}."
    )
    assert not roster_rows.enrollments_for(
        decoyed
    ), f"The member {decoyed!r} reached the database from a page advertised only as `prev`."
    assert roster_rows.enrollments_for(first), (
        f"The first page's own member {first!r} has no enrollment, so this walk ended without "
        "ingesting anything and the denials above hold of a sync that did nothing."
    )
    recorded = roster_rows.calls_for(synced_section.id)
    assert len(recorded) == 1 and all(row.get("response_code") == 200 for row in recorded), (
        f"A single-page container left `nrps_call` rows {[dict(row) for row in recorded]}. D9 "
        "makes it one row per HTTP call carrying the code the platform answered, so a walk that "
        "ended completely leaves exactly one 200 here — more rows is a walk that kept going, and "
        "another code is a completed walk that reads on §6.1's console as a failing one."
    )


def test_a_next_page_that_cannot_be_fetched_ends_the_walk_incomplete_and_recorded(
    roster_sync: Any,
    synced_section: Any,
    service_wire: Any,
    compose_a_roster: Any,
    committed_rows: Any,
    roster_rows: Any,
    roster_contract: Any,
    a_subject: Any,
) -> None:
    """The refused half's pair: a next page the platform advertises and cannot serve.

    "A next URL that cannot be fetched still ends it incomplete." The existing
    truncated-walk safety is asserted next door for an address the *rules* refuse —
    `test_a_next_page_the_platform_points_off_its_own_host_is_refused` — and that is
    a URL never fetched at all. This is the other one: a legitimate URL on the
    platform's own host, fetched, answered with an error. Nothing in the suite pins
    it today.

    Two things have to be true and they pull in opposite directions, which is why
    they are one test. What the walk already ingested stays — a page-boundary
    failure that discarded the whole container would lose a class that synced
    correctly up to it, every hour. And the failure is recorded with the status the
    platform answered, because D9 gives `response_code` NULL exactly one meaning, a
    call that never reached the platform, and a page that answered 500 reached it.

    **The mutation this kills**: swallowing a failed page as the end of the
    container — which is the same silent truncation H1 is about, arriving by a
    different door and leaving an operator with a section that looks complete.
    """
    first = a_subject("first-page")
    following = page_url(synced_section, NEXT_PAGE_PATH)
    service_wire.serve(
        compose_a_roster(synced_section, [roster_contract.member(first)], next_url=following)
    )
    service_wire.failing(following, 500)

    during, _ = sync(roster_sync, synced_section, service_wire, committed_rows)

    assert following in gets(during), (
        f"The walk never asked for {following!r}, so nothing here is about a page that could not "
        f"be fetched. It fetched {gets(during)}. `quoted-rel-only` is required to be followed by "
        "`test_the_walk_follows_the_next_relation_whatever_else_the_link_header_carries`, and this "
        "test cannot pose its question until that one passes."
    )
    assert roster_rows.enrollments_for(first), (
        f"The first page's member {first!r} was not ingested after the *second* page answered 500. "
        "A walk that throws away the container it already has because a later page failed loses "
        "the whole class on every hourly run, and the loss is invisible."
    )
    recorded = roster_rows.calls_for(synced_section.id)
    assert [row for row in recorded if row.get("response_code") == 500], (
        f"The next page answered 500 and the section's `nrps_call` rows are "
        f"{[dict(row) for row in recorded]}. SPEC §6.1 puts 'NRPS and AGS call logs with response "
        "codes' on the admin console, and D9 makes NULL mean a call that never reached the "
        "platform — so a fetched page that failed and left no row, or a row with no code, is a "
        "truncated roster an operator has no way to see."
    )


# ---------------------------------------------------------------------------
# What "incomplete" is worth: the two failures, and the member neither of them
# may close.
# ---------------------------------------------------------------------------


def test_an_incomplete_walk_closes_no_enrollment_window(
    roster_sync: Any,
    synced_section: Any,
    service_wire: Any,
    compose_a_roster: Any,
    committed_rows: Any,
    roster_rows: Any,
    roster_contract: Any,
    seed_a_member: Any,
    a_subject: Any,
) -> None:
    """What a truncated walk costs if it is mistaken for a finished one.

    **The mutation this kills**: reporting the failed walk as complete — the
    battery's `return members, True`, which survived every test in this module and
    in the tree. Completeness is not a bookkeeping flag: it is the licence to close
    the enrollment of every member the walk did not see. A platform whose second
    page fails for one hour would end the enrollment of everyone on it, and SPEC
    §3.4's "was this student enrolled in week N" would answer no for a class that
    never left.

    The member here was synced three weeks ago and lives on the page that fails, so
    the walk genuinely never sees them. After a failed walk their window is still
    open, because nothing was learned about them.

    **The pair, cited rather than copied**: a walk that really is complete and that
    really has lost a member does close them, in
    `test_the_roster_sync_records_enrollment_windows.py::test_a_member_who_vanishes_
    from_the_roster_is_ended_at_the_syncs_own_date`. Without that half this test is
    satisfied by a sync that never closes anybody, which is the opposite defect and
    just as expensive.

    The window is read before the walk as well as after it. A member seeded already
    closed would satisfy the assertion below for a reason that has nothing to do
    with the walk (`docs/MISTAKES.md` entry 3).
    """
    returning = a_subject("synced-three-weeks-ago")
    seed_a_member(synced_section, returning, started_on=weeks_ago(3))
    first = a_subject("first-page")
    following = page_url(synced_section, NEXT_PAGE_PATH)
    service_wire.serve(
        compose_a_roster(synced_section, [roster_contract.member(first)], next_url=following)
    )
    service_wire.failing(following, 500)

    opened = one_enrollment(roster_rows, returning)
    assert opened[roster_contract.ended_on_column] is None, (
        f"The seeded member's enrollment is already closed "
        f"({opened[roster_contract.ended_on_column]!r}) before the walk ran, so the assertion below "
        "would hold whatever the sync did."
    )

    during, _ = sync(roster_sync, synced_section, service_wire, committed_rows)

    assert following in gets(during), (
        f"The walk never asked for {following!r}, so it never met the failure that makes it "
        f"incomplete. It fetched {gets(during)}."
    )
    after = one_enrollment(roster_rows, returning)
    assert after[roster_contract.ended_on_column] is None, (
        f"A walk that could not fetch its second page closed {returning!r}: "
        f"`{roster_contract.ended_on_column}` is {after[roster_contract.ended_on_column]!r}. That "
        "member is on the page that failed, so the sync learned nothing about them — and closing "
        "an enrollment on the strength of a page that never arrived ends the enrollment of every "
        "member of every page a platform fails to serve. A walk that did not finish may not be "
        "read as a roster that shrank."
    )


def test_a_transport_failure_on_a_later_page_keeps_the_pages_already_read(
    roster_sync: Any,
    synced_section: Any,
    service_wire: Any,
    compose_a_roster: Any,
    committed_rows: Any,
    roster_rows: Any,
    roster_contract: Any,
    seed_a_member: Any,
    a_subject: Any,
) -> None:
    """The failure that never reaches a status line, which nothing else here drives.

    Every other failure in this module arrives as an HTTP status, because
    `ServiceWire` answers every request with a well-formed response. A platform's
    host that stops answering — a refused connection, a reset, a name that stops
    resolving — reaches the client as `requests.RequestException` and nothing else,
    and reverting that handler to discarding the whole container survived the
    battery.

    **The mutation this kills**: `return None` from the transport branch — the walk
    throws away every page it had already read, so a class whose second page timed
    out syncs as no members at all. Paired with the mutation the test above kills,
    the two ends of the same handler: discarding what was read, and pretending what
    was not read was empty.

    Two things are asserted, and the second is the one the status-code tests cannot
    reach. The first page's member survives. And the member the walk never got to
    is not closed — a transport failure is not news about anybody's enrollment.
    """
    returning = a_subject("synced-three-weeks-ago")
    seed_a_member(synced_section, returning, started_on=weeks_ago(3))
    first = a_subject("first-page")
    following = page_url(synced_section, NEXT_PAGE_PATH)
    service_wire.serve(
        compose_a_roster(synced_section, [roster_contract.member(first)], next_url=following)
    )
    session, refused = a_session_that_cannot_reach(service_wire, following)

    sync(roster_sync, synced_section, service_wire, committed_rows, http=session)

    assert refused.attempts, (
        f"Nothing reached the adapter mounted at {following!r}, so no transport failure happened "
        'and this test is about an ordinary walk. Either the walk did not follow the `rel="next"` '
        "header, or the session it was handed is not the one this test mounted."
    )
    assert roster_rows.enrollments_for(first), (
        f"The first page's member {first!r} was not ingested after the connection to the second "
        "page was refused. The container that had already arrived was discarded because a later "
        "request failed at the socket, so a platform with one bad minute syncs the class to empty."
    )
    after = one_enrollment(roster_rows, returning)
    assert after[roster_contract.ended_on_column] is None, (
        f"A walk whose second page could not be connected to closed {returning!r}: "
        f"`{roster_contract.ended_on_column}` is {after[roster_contract.ended_on_column]!r}. A "
        "connection this tool could not make is not evidence that a student left."
    )


# ---------------------------------------------------------------------------
# The header's own name, and its quoted parameter values.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("spelling", LINK_HEADER_NAMES)
def test_the_walk_follows_the_next_relation_however_the_header_name_is_spelled(
    roster_sync: Any,
    synced_section: Any,
    service_wire: Any,
    compose_a_roster: Any,
    committed_rows: Any,
    roster_rows: Any,
    roster_contract: Any,
    a_subject: Any,
    spelling: str,
) -> None:
    """RFC 9110 §5.1: a field name is case-insensitive, and platforms send `Link`.

    **The mutation this kills**: a reader that looks up the header under exactly
    `link`. Every test in this module passed against it, because this module's own
    machinery had only ever *served* the name in lower case — the fixture was
    supplying the value under test, which is `docs/MISTAKES.md` entry 30 and which
    is why the case is now a parameter rather than a constant.

    `Link` is RFC 8288's own spelling and the one Canvas and Moodle send, so the
    narrowed reader fails against every real platform while every test here stays
    green. `LiNk` is legal too and is here because a fix that lower-cases the name
    it looks for and a fix that hard-codes `Link` are one line apart. `link` is the
    instrument's own case: it is what the rest of this module serves, so a red on
    that parameter alone means the machinery broke rather than the reader.

    The header is required to have arrived under the spelling this test served
    before the walk is asserted about: `requests` reads a response's headers
    case-insensitively, so a wire that normalised the name on the way through would
    make this parameter indistinguishable from the one below it.
    """
    first = a_subject("first-page")
    second = a_subject("second-page")
    following = page_url(synced_section, NEXT_PAGE_PATH)
    service_wire.serve(
        HeaderRewritten(
            compose_a_roster(synced_section, [roster_contract.member(first)]),
            f'<{following}>; rel="next"',
            name=spelling,
        )
    )
    service_wire.serve(
        served_at(
            compose_a_roster(synced_section, [roster_contract.member(second)]), NEXT_PAGE_PATH
        )
    )

    answered = service_wire.session().get(str(synced_section.address))
    assert spelling in dict(answered.headers), (
        f"The first page's headers arrived as {sorted(dict(answered.headers))} and this test served "
        f"the paging header as {spelling!r}. Something between the wire and the client has "
        "re-spelled the name, so this parameter is no longer about the spelling it names."
    )

    during, _ = sync(roster_sync, synced_section, service_wire, committed_rows)

    assert following in gets(during), (
        f"With the paging header named {spelling!r}, the walk fetched {gets(during)} and never "
        f"{following!r}. RFC 9110 §5.1 makes a field name case-insensitive; RFC 8288 §3 spells this "
        "one `Link`, which is what a real platform sends — a reader that matches one casing ends "
        "every roster at its first page against every platform in the field, and leaves this whole "
        "module green."
    )
    assert roster_rows.enrollments_for(
        second
    ), f"The next page's member {second!r} has no enrollment, from a header named {spelling!r}."


def test_a_quoted_parameter_value_carrying_a_comma_does_not_end_the_link(
    roster_sync: Any,
    synced_section: Any,
    service_wire: Any,
    compose_a_roster: Any,
    committed_rows: Any,
    roster_rows: Any,
    roster_contract: Any,
    a_subject: Any,
) -> None:
    """A comma inside a quoted parameter value is a character, not a separator.

    RFC 9110 §5.6.4 defines the quoted-string, and RFC 8288 §3 builds the `Link`
    header's parameters on it: inside quotation marks a comma is part of the value.
    A platform whose page title is `Page 2, of 9` sends exactly this header, and it
    is a header a tool has to read.

    **The mutation this kills**: splitting the header on commas before the quoting
    is accounted for. The link ends in the middle of its own title, the `rel="next"`
    that follows belongs to a fragment with no URL, and the walk ends *complete* —
    the same silent truncation H1 is about, reached through a spelling the
    specification explicitly permits rather than through a bug in a library.

    **The guards come first and they are about this test's own string**, because no
    parser in this repository can serve as the oracle here: E0-15's `link_relations`
    splits parameters at the comma exactly as the defect does, so using it as the
    control would confirm the defect rather than the header. What is checked instead
    is structural and needs no parser — the header names one link, its only comma
    lies between the title's quotation marks, and the `rel="next"` parameter is
    outside them.
    """
    first = a_subject("first-page")
    second = a_subject("second-page")
    following = page_url(synced_section, NEXT_PAGE_PATH)
    header = f'<{following}>; title="{A_QUOTED_COMMA_TITLE}"; rel="next"'

    opening = header.index('"')
    closing = header.index('"', opening + 1)
    assert header.count("<") == 1 and header.count(",") == 1, (
        f"This test's header {header!r} does not carry exactly one link and one comma, so what it "
        "poses is not the case it is named after."
    )
    assert opening < header.index(",") < closing, (
        f"The comma in {header!r} is not inside the quoted title, so this header really does "
        "declare two links and a parser that split it would be right."
    )
    assert header.index('rel="next"') > closing, (
        f'The `rel="next"` in {header!r} is inside the quoted title rather than a parameter of '
        "the link, so the platform is not declaring a next page at all."
    )

    service_wire.serve(
        HeaderRewritten(compose_a_roster(synced_section, [roster_contract.member(first)]), header)
    )
    service_wire.serve(
        served_at(
            compose_a_roster(synced_section, [roster_contract.member(second)]), NEXT_PAGE_PATH
        )
    )

    during, _ = sync(roster_sync, synced_section, service_wire, committed_rows)

    assert following in gets(during), (
        f"The platform declared its next page with a quoted title carrying a comma "
        f"({header!r}) and the walk fetched {gets(during)}. Inside a quoted-string a comma is a "
        "character (RFC 9110 §5.6.4), so this is one link declaring `next` — and a reader that "
        "takes the header apart at commas first ends the roster here, reports nothing, and leaves "
        "the section short in a way no operator can see."
    )
    assert roster_rows.enrollments_for(second), (
        f"The next page's member {second!r} has no enrollment from a link whose title contains a "
        "comma."
    )


def test_a_relation_spelled_inside_a_quoted_parameter_value_is_not_a_next_page(
    roster_sync: Any,
    synced_section: Any,
    service_wire: Any,
    compose_a_roster: Any,
    committed_rows: Any,
    roster_rows: Any,
    roster_contract: Any,
    a_subject: Any,
) -> None:
    """The other direction of the same defect, and it is the platform choosing.

    A link the platform declares `prev`, whose *title* contains the text
    `rel=next`. A reader that searches the raw header for the relation, or that
    splits a link's parameters at semicolons without accounting for quotation
    marks, finds the relation inside the title and follows a URL the platform did
    not offer as a next page.

    **Why that is a security property and not a paging one.** The tool's Bearer
    token goes with every page it fetches, and the URL it is sent to is now
    determined by a string inside a quoted value rather than by the relation the
    platform declared. Every address rule still applies — this is not the same
    finding as a hostile URL — but which of a platform's own advertised addresses
    the tool walks into, and how many times, stops being the platform's stated
    intent.

    **The mutation this kills**: a relation match run over the header text, or over
    parameters split at `;` with no quoting rule. The `three-links-in-one-header`
    case above passes against both.

    **The guards are structural, for the reason the test above gives**: both parsers
    available in this repository share the defect, so neither can be the oracle.
    What is checked is that this module's own decoy segment declares `prev` and that
    its `rel=next` text lies strictly inside the quoted title.
    """
    first = a_subject("first-page")
    second = a_subject("second-page")
    decoyed = a_subject("decoy-page")
    following = page_url(synced_section, NEXT_PAGE_PATH)
    decoy = page_url(synced_section, DECOY_PAGE_PATH)
    decoy_segment = f'<{decoy}>; title="{A_QUOTED_RELATION_TITLE}"; rel="prev"'
    header = f'{decoy_segment}, <{following}>; rel="next"'

    quotes = [index for index, character in enumerate(decoy_segment) if character == '"']
    hidden = decoy_segment.index("rel=next")
    assert quotes[0] < hidden < quotes[1], (
        f"The `rel=next` in {decoy_segment!r} is not inside the quoted title, so the platform "
        "really is declaring this link a next page and following it would be correct."
    )
    assert decoy_segment.endswith('rel="prev"'), (
        f"{decoy_segment!r} does not declare the decoy link as `prev`, so the assertion below is "
        "not about a relation the platform declared."
    )

    service_wire.serve(
        HeaderRewritten(compose_a_roster(synced_section, [roster_contract.member(first)]), header)
    )
    service_wire.serve(
        served_at(
            compose_a_roster(synced_section, [roster_contract.member(second)]), NEXT_PAGE_PATH
        )
    )
    service_wire.serve(
        served_at(
            compose_a_roster(synced_section, [roster_contract.member(decoyed)]), DECOY_PAGE_PATH
        )
    )

    during, _ = sync(roster_sync, synced_section, service_wire, committed_rows)

    assert decoy not in gets(during), (
        f"The walk fetched {decoy!r}, which this platform declared as `prev`. The only place the "
        f"text `rel=next` appears for that link is inside its quoted title ({decoy_segment!r}), so "
        "the tool is taking its instructions from a value the platform quoted rather than from the "
        f"relation the platform declared. It fetched {gets(during)}."
    )
    assert not roster_rows.enrollments_for(
        decoyed
    ), f"The member {decoyed!r} was ingested from the page declared `prev`."
    assert roster_rows.enrollments_for(second), (
        f"The real next page's member {second!r} has no enrollment. The header declares `next` at "
        f"{following!r} after the decoy, so a reader that stopped at the decoy — or that read the "
        "quoted title as the relation — never reached the page the platform actually offered."
    )
