"""Where the mock platform is smoother than the platforms it stands in for — E0-28.

E0-15 built NRPS 2.0 and AGS 2.0 on the platform side and its review found eight
places where the mock is *more forgiving, or more uniform*, than a real LMS. That
is the whole subject of this module. Nothing here is a defect a user could meet:
every item is a case E1's roster sync or E3's grade passback will write code
against, pass here, and fail against Canvas, Moodle, D2L or Blackboard —
**silently**, because each of those epics tests itself against this mock.

SPEC §7.3 names the two areas where platforms deviate — NRPS paging and AGS score
semantics — and puts the deviations in a `PlatformProfile` adapter. A mock that
smooths them over is a mock that teaches a tool the deviations do not exist.

**The items this module carries**, by the numbering the ticket and the code
comments both use:

  - **2** — NRPS's own `role`, `limit` and `rlid` are refused rather than
    accepted and disregarded. Refusing is E0-28's ruling: accepted-and-ignored is
    the state that lets a tool ship a reliance on filtering no platform
    guarantees.
  - **3, 7, 9** — what a line-item or result URL may look like. Every minted line
    item id carries a query string (Moodle's `type_id`), so a client assembling
    `id + "/scores"` is wrong; `read_line_item` keeps its route and carries the
    round trip that proves the platform serves the id it minted; and a `userId`
    containing a slash routes rather than composing a `resultUrl` the platform
    itself cannot serve.
  - **4, 5, 10** — paging. The results container pages and honours `limit`; a
    single-page container carries the relations that apply (`first`, `last`,
    `current`) with `next` still absent; and both containers serve their cap and
    advertise the rest.

**How a test finds a service.** Out of the launch claims, like its siblings —
`test_mock_lms_nrps_roster.py` explains why at length and nothing here repeats
it. The one URL this module composes rather than reads is the naive
concatenation in `test_the_naive_concatenation_of_a_scores_segment_is_not_a_score_endpoint`,
which exists precisely to be refused.

**Two of these tests are born green, and say so in their own docstrings.** Items
7 and 10 are coverage debt rather than missing behaviour: the route and the clamp
are already there and nothing asserts them, which is `docs/MISTAKES.md` entry 2 —
behaviour shipped with nothing asserting it. Their worth is the mutation each
names, not the colour they start at.

**No §4.1 invariant lives here**, for the reason the roster suite gives: the mock
is a platform, not a Pulse read path.
"""

from typing import Any
from urllib.parse import parse_qs, urljoin, urlsplit

import pytest

pytestmark = pytest.mark.lti

# `mock_platform`, `signed_launch`, `link_relations_in` and `path_appended_to`
# come from `tests/fixtures/lti_services.py` and are reached through fixtures
# rather than imported, for the reason the sibling modules give: a module that
# imports a fixtures module by name depends on where pytest put `tests/` on
# `sys.path`, and
# an import error is a broken suite rather than a red.

# The three NRPS 2.0 query parameters a membership container defines and this
# platform does not implement. **The specification's names, not this suite's** —
# a tool sends exactly these — and E0-28 item 2 rules that each is refused with
# 400 rather than accepted and disregarded.
NRPS_QUERY_PARAMETERS_REFUSED = ("role", "limit", "rlid")

# What a refused parameter is refused *with*. E0-28 item 2's ruling, asserted as
# the exact code rather than "a 4xx": 400 says the platform read the request and
# will not serve it, which is the sentence the tool has to act on, and a 422 from
# a model that could not parse it is a different fact.
REFUSAL_STATUS = 400

# The cursor the container does implement, and the accepted half of item 2's
# boundary pair.
PAGE_PARAMETER = "page"

# The member's identifier, spelled as NRPS 2.0 spells it. The roster suite
# carries the same constant and the same sentence: a container spelling it
# `userId` is one `pylti1p3` reads as a member with no user.
MEMBER_ID = "user_id"

# A role a tool would filter a roster by, spelled from the LIS vocabulary the
# launch's roles claim uses. Its value is beside the point — the request is
# refused whatever it says — but a plausible one keeps the test honest about
# what it is asking for.
INSTRUCTOR_ROLE = "http://purl.imsglobal.org/vocab/lis/v2/membership#Instructor"

# Moodle's own query parameter on a line item id: `…/lineitems/3/lineitem?type_id=1`.
# **Not this suite's name** — E0-28 item 3 mints the querified id with exactly
# this parameter because the point of the item is that a real platform's ids
# carry a query, and inventing a different name would make the fixture a shape
# nobody has to meet.
LINE_ITEM_ID_QUERY_PARAMETER = "type_id"

# The media types NRPS 2.0 and AGS 2.0 fix for these documents. Transcribed from
# the specifications, the way `tests/fixtures/lti_services.py` transcribes them and the AGS
# suite transcribes its scopes: they are published constants rather than a
# decision either file makes.
LINE_ITEM_MEDIA_TYPE = "application/vnd.ims.lis.v2.lineitem+json"
LINE_ITEM_CONTAINER_MEDIA_TYPE = "application/vnd.ims.lis.v2.lineitemcontainer+json"
SCORE_MEDIA_TYPE = "application/vnd.ims.lis.v1.score+json"

# The two caps, **written here rather than imported from `mock-lms/app/ags.py`**,
# and that is `docs/MISTAKES.md` entry 19: a test that reads its expectation out
# of the module under test holds two copies of one fact inside the blast radius
# of one change. `MAX_LINE_ITEM_LIMIT` moved from 100 to 101 *and* imported here
# would leave these tests green, which is the exact mutation E0-28 item 10 exists
# to make loud — the ticket's complaint is that the cap "is a number no test
# names", so the tests name it.
MAX_LINE_ITEM_LIMIT = 100
MAX_RESULT_LIMIT = 100

# How many results one page of the result container holds when a tool asks for no
# limit. E0-28's ruling (`RESULT_PAGE_SIZE`), and the tests that post more than
# this depend on it: a container that pages at 50 would put every score below on
# one page and the boundary assertions would have no boundary to be about.
RESULT_PAGE_SIZE = 5

# A `limit` no platform serves, used to ask both containers for everything. Large
# enough that a cap of any plausible size is what answers.
OVER_LARGE_LIMIT = 10**6

# The score this module posts. The AGS suite explains why each value is chosen to
# be one no implementation reaches by accident; what matters here is only that
# these are accepted, so `gradingProgress` is a value that produces a `Result` —
# a results container is what half these tests page through.
POSTED_TIMESTAMP = "2026-03-02T14:05:09+00:00"
POSTED_SCORE = 61.5
POSTED_MAXIMUM = 100
POSTED_ACTIVITY_PROGRESS = "Completed"
POSTED_GRADING_PROGRESS = "FullyGraded"

# The two user identifiers E0-28 item 9 is about, and they are a pair rather than
# one case. `a/b` is the `sub` that makes `result_url` compose `…/results/a%2Fb`,
# which Starlette answers 404 for because ASGI hands the router the *decoded*
# path. `a%2Fb` is a different user whose identifier happens to be the first
# one's encoding — the near miss, because a route that decodes once too often
# collapses the two into one student's grade.
SLASHED_USER_ID = "a/b"
LITERALLY_ENCODED_USER_ID = "a%2Fb"


def score_payload(user_id: str, **overrides: Any) -> dict[str, Any]:
    """One AGS score, spelled as AGS 2.0 spells it.

    The same five members the AGS suite posts — `userId`, an RFC 3339
    `timestamp` carrying an offset, `activityProgress`, `gradingProgress`, and
    `scoreGiven` paired with a `scoreMaximum` equal to the line item's. The pair
    matters: E0-15 refuses a `scoreGiven` with no maximum and refuses a maximum
    that disagrees with the line item's, so a score built any other way would be
    testing those rules rather than the paging and the URLs.
    """
    payload: dict[str, Any] = {
        "userId": user_id,
        "timestamp": POSTED_TIMESTAMP,
        "scoreGiven": POSTED_SCORE,
        "scoreMaximum": POSTED_MAXIMUM,
        "activityProgress": POSTED_ACTIVITY_PROGRESS,
        "gradingProgress": POSTED_GRADING_PROGRESS,
    }
    payload.update(overrides)
    return payload


def accepted_score(platform: Any, line_item: dict[str, Any], user_id: str) -> Any:
    """Post one score and require the platform to take it.

    Every test below that reads a results container needs results in it, and a
    post refused for a reason the test is not about would leave the container
    empty — which satisfies most assertions about what a container does not
    carry (`docs/MISTAKES.md` entry 3). So the acceptance is asserted here, once,
    and the message names the decision a refusal would be reversing: E0-28 item 9
    rules that this platform *serves* the user identifier a tool sends it, taking
    the round trip rather than narrowing AGS at the score post.
    """
    response = platform.post_score(line_item, score_payload(user_id))
    assert 200 <= response.status_code < 300, (
        f"Posting a score for {user_id!r} answered {response.status_code}, so there is no result "
        f"to read back. Body begins {response.text[:200]!r}. If the platform is refusing a user "
        "it has no enrollment for, that is a narrowing of AGS that E0-28 item 9 considered and "
        "rejected — it is a sentence the ticket owes rather than something to work around here."
    )
    return response


def result_users(results: list[dict[str, Any]]) -> list[str]:
    """The `userId` of each result, in the order the container served them."""
    return [str(result.get("userId", "")) for result in results]


def many_scored_users(platform: Any, line_item: dict[str, Any], count: int) -> list[str]:
    """Post one accepted score each for `count` distinct users, and name them.

    Minted for the test rather than taken from the seed, which E0-28 item 10
    requires in as many words — the seed stays small, and a container over the
    cap is built by the test that needs one.
    """
    users = [f"e0-28-user-{ordinal:03d}" for ordinal in range(1, count + 1)]
    for user_id in users:
        accepted_score(platform, line_item, user_id)
    return users


def walked_rosters(platform: Any) -> list[tuple[Any, list[Any]]]:
    """Every seeded context paired with its fully walked roster.

    Fails rather than answering an empty list, for the reason the roster suite's
    twin of this helper does: every assertion below is over the pages it returns
    and an empty walk satisfies most of them.
    """
    contexts = platform.seeded_contexts()
    assert contexts, (
        "The launch page offers no launches, so this suite found no roster to read a `Link` "
        "header off. E0-14 seeds the launches and E0-15 seeds the rosters behind them."
    )
    return [(context, platform.membership_pages(context.memberships_url)) for context in contexts]


def member_ids(page: Any) -> list[str]:
    """The identifiers on one membership page, in the order it served them."""
    return [str(member.get(MEMBER_ID)) for member in page.members]


# ---------------------------------------------------------------------------
# The controls on this module's own new machinery. Both must be green: a red
# here is this suite being broken rather than the platform being wrong, and the
# tests below it are then reporting nothing about E0-28.
# ---------------------------------------------------------------------------


def test_the_path_insertion_helper_puts_the_segment_before_the_query(
    path_appended_to: Any,
) -> None:
    """The control on `path_appended`, which every AGS service URL below is built with.

    **A red here means the tests are broken, not the code.** This asserts nothing
    about the mock platform: it is arithmetic on a URL, run against the shapes it
    is claimed to handle and the shape it exists for, so that the item-3
    assertions below cannot pass or fail for a reason that is really this
    helper's (`docs/MISTAKES.md` entry 3 — run the thing against what it must
    handle as well as what it must catch).

    Three cases, and the second is the whole point. A bare id must come out
    exactly as concatenation would, or landing this helper would move an existing
    assertion; a querified id must take the segment in its *path*; and a
    trailing slash must not produce a doubled one, because a platform is free to
    mint either spelling.
    """
    assert path_appended_to("https://p.invalid/lineitems/3", "scores") == (
        "https://p.invalid/lineitems/3/scores"
    ), "A bare line item id takes the segment on the end, exactly as concatenation would."
    assert path_appended_to("https://p.invalid/lineitems/3/lineitem?type_id=1", "scores") == (
        "https://p.invalid/lineitems/3/lineitem/scores?type_id=1"
    ), (
        "A line item id carrying a query takes the segment before the query. Concatenation "
        "produces `…/lineitem?type_id=1/scores`, which is a request to the line item itself with "
        "a nonsense query — well-formed, answerable, and it posts no score anywhere."
    )
    assert path_appended_to("https://p.invalid/lineitems/3/?type_id=1", "results") == (
        "https://p.invalid/lineitems/3/results?type_id=1"
    ), "A trailing slash on the id does not become a doubled slash in the service URL."


def test_the_result_container_walk_returns_the_one_page_a_small_container_fits_on(
    mock_platform: Any,
    signed_launch: Any,
) -> None:
    """The control on `result_pages`, the walk E0-28 item 4's tests are read through.

    **A red here means the tests are broken, not the code.** A walk that stopped
    after its first page, or that read the results out of the wrong member of the
    document, would make every paging assertion below a statement about page one
    — and page one is where a container that does not page puts everything. So
    the walk is shown agreeing with the single-page reader on a container that
    demonstrably fits on one page, before either is believed about a container
    that does not.
    """
    created = mock_platform.create_line_item(signed_launch)
    accepted_score(mock_platform, created, "e0-28-control-user")

    pages = mock_platform.result_pages(created)
    assert len(pages) == 1, (
        f"One score was posted to `{created.get('id')}` and the walk returned {len(pages)} pages "
        f"({[len(page.results) for page in pages]} results each). One result fits on any page "
        "size, so more than one page here is the walk following a `next` relation that points at "
        "nothing new — and every assertion below reads through this walk."
    )
    assert result_users(pages[0].results) == result_users(mock_platform.results(created)), (
        f"The walk read {result_users(pages[0].results)} off the container and the single-page "
        f"reader read {result_users(mock_platform.results(created))}. The two disagree about what "
        "one page carries, so neither can be trusted about what several do."
    )


# ---------------------------------------------------------------------------
# Item 2 — NRPS's own query parameters are refused rather than disregarded.
# ---------------------------------------------------------------------------


def test_the_roster_refuses_the_nrps_query_parameters_it_does_not_implement(
    mock_platform: Any,
    signed_launch: Any,
) -> None:
    """Item 2: `role`, `limit` and `rlid` answer 400, each naming the parameter.

    **The mutation is FastAPI's default tolerance**, which is what the container
    does today: a parameter the handler does not declare is dropped, the request
    answers 200, and the roster comes back whole. A tool asking for
    `role=…#Instructor` is handed every member of the page and cannot tell that
    from a section where everyone teaches. E1 then ships a sync that relies on
    server-side filtering, and meets the first platform that ignores these —
    which is permitted, and is why a tool must filter client-side anyway.

    Refusing is E0-28's ruling over implementing `role`, and the reason is the
    one E0-30 item 4 gives: accepted-and-ignored is the state a tool cannot
    detect, while a 400 is a sentence the tool's author reads once and acts on.

    The parameter has to be **named in the body**, which is the near miss here: a
    blanket "this container takes no filters" refusal is indistinguishable, in a
    log, from the container being broken, and a tool sending two parameters
    cannot learn which one this platform objects to.

    Each parameter is asserted on its own request rather than all three together,
    because a handler that checks the first name it sees and returns is right
    about a request carrying all three and wrong about two requests in three.
    """
    url = mock_platform.memberships_url(signed_launch)
    for parameter, value in (
        ("role", INSTRUCTOR_ROLE),
        ("limit", "2"),
        ("rlid", "e0-28-resource-link"),
    ):
        # `roster_get` rather than `service_get`: since E1-11's fix round the
        # mock's NRPS route requires an access token, and a tokenless call would
        # be answered 401 before it ever reached the filter this test is about.
        response = mock_platform.roster_get(
            mock_platform.with_query(url, {parameter: value}), accept=None
        )
        assert response.status_code == REFUSAL_STATUS, (
            f"Asking the membership container for `{parameter}={value}` answered "
            f"{response.status_code} rather than {REFUSAL_STATUS}. Body begins "
            f"{response.text[:200]!r}. E0-28 item 2: NRPS's own parameters either work or are "
            "refused — accepted and disregarded is the one state a tool cannot detect, and it is "
            "what lets a reliance on server-side filtering ship."
        )
        assert parameter in response.text.lower(), (
            f"The refusal of `{parameter}={value}` does not name `{parameter}` — the body is "
            f"{response.text[:300]!r}. A refusal that does not say which parameter it objects to "
            "reads, from the tool's side, as the container being broken; item 2 asks for a "
            "message naming the parameter and saying that a tool must filter client-side."
        )


def test_the_roster_still_pages_by_the_parameter_it_does_implement(
    mock_platform: Any,
    signed_launch: Any,
) -> None:
    """The accepted half of item 2's pair, and it is not ceremony.

    A container that answered 400 to *every* query parameter would pass the
    refusal test above completely, and would break the one cursor this platform
    has: `page` is how E0-15's own roster walk moves, so a blanket refusal turns
    every seeded roster into its first page and the whole NRPS suite into a
    statement about page one.

    `docs/MISTAKES.md` entry 3 in its plainest form — run the rule against what
    it must refuse *and* what it must allow — and the two halves are separate
    tests so the runner line says which way the container went wrong.
    """
    url = mock_platform.memberships_url(signed_launch)
    # `roster_get` for the reason its twin above gives: the roster is behind a
    # token since E1-11's fix round, and a tokenless read is 401 rather than 200.
    response = mock_platform.roster_get(
        mock_platform.with_query(url, {PAGE_PARAMETER: 1}), accept=None
    )
    assert response.status_code == 200, (
        f"Asking the membership container for `{PAGE_PARAMETER}=1` answered "
        f"{response.status_code}. Body begins {response.text[:200]!r}. E0-28 item 2 refuses "
        f"`role`, `limit` and `rlid` and leaves `{PAGE_PARAMETER}` working — it is the cursor the "
        "roster walk moves by, so refusing it stops every paging test in this repository from "
        "reaching page two."
    )
    page = mock_platform.membership_page_of(url, response)
    assert page.members, (
        f"`{PAGE_PARAMETER}=1` answered 200 with no members: {page.document!r}. A cursor that is "
        "accepted and serves nothing is the same defect as one that is refused, wearing a status "
        "code that says otherwise."
    )


# ---------------------------------------------------------------------------
# Item 3 — a line item id carries a query, and the scores URL is not a
# concatenation. Item 7 rides here too, on the id the platform minted.
# ---------------------------------------------------------------------------


def test_every_minted_line_item_id_carries_a_query_string(
    mock_platform: Any,
    signed_launch: Any,
) -> None:
    """Item 3: the fixture that makes the naive concatenation wrong.

    **The mutation is the platform as it stands**: every id it mints is a bare
    path, so `id + "/scores"` is right here forever and E3 can ship it with a
    green suite. Moodle's ids carry `?type_id=1` and the segment goes before it,
    which is a passback that posts nowhere — against the platform with the
    largest share of the sector the tool has no route to.

    The parameter is asserted by name rather than as "some query", because a
    query the platform invented for itself is a fixture that looks like the
    hazard and is not one: `type_id` is Moodle's own parameter, so a client that
    handles this id handles the real one.

    Both created line items are checked, which kills the near miss of one
    querified id minted for the test to find while the container goes on
    handing out bare ones — E3 reads ids out of the container, not out of the
    creation response.
    """
    for created in (
        mock_platform.create_line_item(signed_launch),
        mock_platform.create_line_item(signed_launch),
    ):
        identifier = str(created.get("id"))
        query = urlsplit(identifier).query
        assert query, (
            f"The line item minted at `{identifier}` carries no query string. E0-28 item 3: at "
            "least one line item id carries one, so that a client assembling a scores URL by "
            "concatenation is wrong here rather than only against Moodle — where the id is "
            "`…/lineitems/3/lineitem?type_id=1` and `/scores` goes before the query."
        )
        assert LINE_ITEM_ID_QUERY_PARAMETER in parse_qs(query), (
            f"The line item id `{identifier}` carries a query that is not "
            f"`{LINE_ITEM_ID_QUERY_PARAMETER}` — it carries {sorted(parse_qs(query))}. The "
            "parameter is Moodle's own, which is what makes this fixture the hazard a tool has "
            "to meet rather than one this repository invented."
        )


def test_the_scores_url_built_by_inserting_the_segment_before_the_query_is_accepted(
    mock_platform: Any,
    signed_launch: Any,
    path_appended_to: Any,
) -> None:
    """Item 3's modelled client: the assembly a conformant tool has to make.

    E0-28 item 3 asks for "a test that a client assembling the scores URL handles
    it", and the client is `MockPlatform.scores_url` — every score this
    repository posts goes through it. So this asserts what that assembly produces
    and that the platform takes a score at it.

    **The mutation is the helper reverting to concatenation**, which is the shape
    it replaced and the shape E3 would otherwise write. It kills nothing today
    and everything once ids carry a query, which is exactly why the two land in
    one change.

    The platform is required to *record* the score rather than merely answer
    2xx: a route that matched the wrong path and answered 200 for another reason
    is a green this test would otherwise report.
    """
    created = mock_platform.create_line_item(signed_launch)
    identifier = str(created.get("id"))
    built = mock_platform.scores_url(created)

    assert built == path_appended_to(identifier, "scores"), (
        f"`MockPlatform.scores_url` produced `{built}` for the id `{identifier}` while the "
        "insertion helper produces "
        f"`{path_appended_to(identifier, 'scores')}`. The modelled client and the helper its "
        "control test checks have come apart, so neither says anything about the other."
    )
    assert urlsplit(built).path.endswith("/scores"), (
        f"The scores URL `{built}` does not carry `/scores` in its *path*. AGS 2.0 derives the "
        "Score service from the line item's URL by adding that segment to the path; a `/scores` "
        "that has landed in the query string is a request to the line item itself."
    )
    assert urlsplit(built).query == urlsplit(identifier).query, (
        f"The scores URL `{built}` has lost or changed the query the line item id `{identifier}` "
        "carries. Moodle's `type_id` identifies the line item; dropping it addresses a different "
        "one, or none."
    )

    accepted_score(mock_platform, created, "e0-28-scores-url-user")
    recorded = mock_platform.posted_scores_for(created)
    assert len(recorded) == 1, (
        f"A score posted to `{built}` was accepted and `/mock/posted-scores` reports "
        f"{len(recorded)} entries for line item `{identifier}`: {recorded!r}. A 2xx from a route "
        "that recorded nothing is a passback reporting success and posting nowhere."
    )


def test_the_naive_concatenation_of_a_scores_segment_is_not_a_score_endpoint(
    mock_platform: Any,
    signed_launch: Any,
) -> None:
    """The other half of item 3's pair: the wrong assembly has to be *wrong here*.

    This is the assertion that makes the criterion enforceable. "The correct URL
    works" is satisfied by a platform whose ids are bare paths, where correct and
    naive are the same string — which is the state E0-28 item 3 exists to leave.
    So the naive concatenation is posted deliberately and required to fail: with
    a querified id, `…/3?type_id=3` + `/scores` is a request to the line item
    carrying the query `type_id=3/scores`, which no Score service serves.

    **The near miss is a platform that answers it anyway** — a route tolerant
    enough to treat the line item URL as its own score endpoint — so the log is
    read as well as the status: a score that was refused and recorded is worse
    than one accepted, because the tool retries what it believes failed.
    """
    created = mock_platform.create_line_item(signed_launch)
    identifier = str(created.get("id"))
    naive = f"{identifier.rstrip('/')}/scores"
    assert naive != mock_platform.scores_url(created), (
        f"Concatenating `/scores` onto `{identifier}` produces the same URL as inserting it "
        f"(`{naive}`), so this line item id carries no query and the naive assembly cannot be "
        "wrong here. E0-28 item 3 mints an id that makes the two differ; without one, E3 ships "
        "the concatenation with a green suite."
    )

    before = mock_platform.posted_scores_for(created)
    response = mock_platform.service_post(
        naive, score_payload("e0-28-naive-user"), SCORE_MEDIA_TYPE
    )
    assert 400 <= response.status_code < 500, (
        f"Posting a score to the naively concatenated `{naive}` answered "
        f"{response.status_code}. Body begins {response.text[:200]!r}. That URL addresses the "
        "line item itself with a nonsense query rather than its Score service, and a platform "
        "that takes a score there teaches a tool an assembly no other platform accepts."
    )
    after = mock_platform.posted_scores_for(created)
    assert len(after) == len(before), (
        f"The post to `{naive}` was refused with {response.status_code} and recorded anyway: "
        f"{len(before)} scores before and {len(after)} after."
    )


def test_the_read_line_item_route_answers_the_exact_identifier_the_platform_minted(
    mock_platform: Any,
    signed_launch: Any,
) -> None:
    """Item 7's criterion, carried on item 3's querified id. **Born green.**

    **What the route is for**, which is what item 7 asks for in as many words:
    `GET <lineitem>` is defined by AGS 2.0, and E3's line-item reconciliation
    reads it — a tool that holds an id from a previous term needs to ask whether
    that line item still exists and still has the maximum it was created with,
    without listing a container and searching it. E0-28 keeps the route for that
    reason rather than deleting a conformant endpoint and re-adding it one epic
    later.

    **The mutation: delete the route.** This test goes red and nothing else in
    the repository moves, which is the whole of why it exists — the route was
    served and driven by nobody, which is `docs/MISTAKES.md` entry 2.

    **The second mutation is item 3's**, and it is why this test carries the id
    rather than a path: the platform must serve the exact identifier it minted,
    query and all. A platform that mints `…/3?type_id=3` and routes only `…/3`
    has handed a tool an id it cannot use — and the failure would surface in E3
    as a 404 on a URL the platform itself composed.

    The media type is asserted because a conformant tool sends `Accept:` and
    branches on what comes back; a route answering `application/json` is one a
    strict client rejects.
    """
    created = mock_platform.create_line_item(signed_launch)
    identifier = str(created.get("id"))

    response = mock_platform.service_get(identifier, accept=LINE_ITEM_MEDIA_TYPE)
    assert response.status_code == 200, (
        f"`GET {identifier}` — the exact identifier the platform minted — answered "
        f"{response.status_code}. Body begins {response.text[:200]!r}. AGS 2.0 defines the "
        "read-line-item route and E3's reconciliation reads it; an id the platform composes and "
        "does not serve is a URL a tool follows once, in the job that needed it."
    )
    assert response.json().get("id") == identifier, (
        f"`GET {identifier}` answered a line item whose `id` is {response.json().get('id')!r}. A "
        "route that serves a document identifying itself as something else hands a tool two ids "
        "for one line item, and E3's reconciliation cannot tell which one to hold."
    )
    assert response.headers.get("content-type", "").startswith(LINE_ITEM_MEDIA_TYPE), (
        f"`GET {identifier}` answered with content type "
        f"{response.headers.get('content-type')!r} rather than `{LINE_ITEM_MEDIA_TYPE}`. AGS 2.0 "
        "fixes the media type of a line item, and a strict client branches on it."
    )


# ---------------------------------------------------------------------------
# Item 4 — the results container pages, and honours `limit`.
# ---------------------------------------------------------------------------


def test_walking_the_results_container_loses_no_result_at_a_page_boundary(
    mock_platform: Any,
    signed_launch: Any,
) -> None:
    """Item 4: a results container bigger than a page is walked the way the roster is.

    **The mutation is the container as it stands** — `read_results` says in its
    own docstring that it does not page — and the consequence is the one the
    ticket spells out: a 200-student section on a platform paging at 50 reads
    back 50 results and 150 apparent non-submitters. E3 would then re-post 150
    grades that were already posted, every week, and its reconciliation would
    never converge.

    Two more mutations, and they are the pair every paged container has. A page
    that overlaps its neighbour repeats a result, which reads as a student
    graded twice; a slice one short of its own boundary loses one result per
    boundary, which reads as a student who never submitted. Both are asserted
    from the walk itself: the users the container serves across its pages must be
    exactly the users whose scores were posted, once each.

    The guard above them is load-bearing. Over a container that came back on one
    page the comparison is `n == n` for any implementation at all, so a platform
    that never learned to page would satisfy this test rather than fail it.
    """
    created = mock_platform.create_line_item(signed_launch)
    posted = many_scored_users(mock_platform, created, RESULT_PAGE_SIZE + 2)

    pages = mock_platform.result_pages(created)
    assert len(pages) > 1, (
        f"{len(posted)} scores were posted for distinct users to one line item and the results "
        f"container came back on {len(pages)} page(s) of "
        f"{[len(page.results) for page in pages]}, advertising no next relation (Link header "
        f"{pages[0].link_header!r}). E0-28 item 4: the container pages with a `Link` header — "
        "without one there is no page boundary for this test to be about, and a tool reading the "
        "first page calls it the class."
    )
    served = [user for page in pages for user in result_users(page.results)]
    repeated = sorted({user for user in served if served.count(user) > 1})
    assert not repeated, (
        f"Walking the {len(pages)} pages of the results container returned {len(served)} results "
        f"of which {repeated} appear more than once. The pages of a container partition it, so a "
        "result on two pages is an offset that moves by less than the page it just served — and "
        "in E3 that is a student whose grade is posted twice."
    )
    assert sorted(served) == sorted(posted), (
        f"The walk assembled {sorted(served)} and the scores posted were for {sorted(posted)}. A "
        "page sliced one short of its own boundary loses a result per boundary, which reads in "
        "the gradebook as a student who never submitted."
    )
    empty = [page for page in pages if not page.results]
    assert not empty, (
        f"The results container came back over {len(pages)} pages and {len(empty)} of them carry "
        f"no results — the first is `{empty[0].url}`, served with Link header "
        f"{empty[0].link_header!r}. A header that advertises a next page whenever the page it is "
        "on is full advertises one page too many."
    )


def test_a_limit_of_two_gives_the_results_container_pages_of_two(
    mock_platform: Any,
    signed_launch: Any,
) -> None:
    """Item 4's `limit`, asserted across the whole walk rather than on page one.

    **The near miss is a `limit` honoured on the first page and lost from the
    `Link` URL the platform advertises about itself.** That is not hypothetical
    in this repository: the line-item container had the same defect in the shape
    of a blank filter dropped by `parse_qsl`, and the AGS suite carries a test
    for it. A tool that asked for pages of two and is served pages of five from
    page two onward is holding more grades per request than it asked for, and any
    rate or memory budget it set is wrong.

    So the assertion is on every page but the last: the last is free to be short,
    and requiring it to hold two would be this test asserting that the container
    divides evenly, which is a fact about the fixture rather than about `limit`.
    """
    created = mock_platform.create_line_item(signed_launch)
    posted = many_scored_users(mock_platform, created, RESULT_PAGE_SIZE + 2)

    pages = mock_platform.result_pages(created, limit=2)
    assert len(pages) > 1, (
        f"Asking the results container for `limit=2` over {len(posted)} results returned "
        f"everything on {len(pages)} page(s) of {[len(page.results) for page in pages]}. Either "
        "the limit was ignored or the rest was never advertised; a tool reading the first page "
        "calls that the whole set."
    )
    assert all(len(page.results) == 2 for page in pages[:-1]), (
        f"With `limit=2`, the pages came back holding {[len(page.results) for page in pages]} "
        "results. A limit that reaches the first page and not the `next` URL the platform "
        "advertises is a limit a tool cannot page on — it asked for two and is served a default "
        "from page two onward."
    )
    served = [user for page in pages for user in result_users(page.results)]
    assert sorted(served) == sorted(posted), (
        f"The `limit=2` walk assembled {sorted(served)} for scores posted as {sorted(posted)}. A "
        "limit that also drops results is a page size and a filter at once."
    )


def test_a_filtered_walk_of_the_results_container_stays_filtered(
    mock_platform: Any,
    signed_launch: Any,
) -> None:
    """The fail-open near miss: `user_id` surviving into the URLs the platform advertises.

    Filtering and paging each have a test and their combination is where they
    interact, because the filter has to survive into every relation the page
    advertises. A container that filters correctly and advertises an unfiltered
    `first`, `last` or `current` hands a tool the whole class the moment it
    follows one of them — and in E3, asking for one student's result and
    receiving everyone's is the shape §4's confidentiality model exists to keep
    out of the tool.

    It fails *open*, which is why it is asserted by following what the platform
    published rather than by reading the URLs' spelling: a relation whose URL has
    lost `user_id` answers with the unfiltered page, and the unfiltered page here
    demonstrably carries other students. The guard that the container holds more
    than one user is what makes that observable — with one scored user the
    unfiltered and filtered pages are the same page, and this test would pass
    against any implementation at all.
    """
    created = mock_platform.create_line_item(signed_launch)
    posted = many_scored_users(mock_platform, created, RESULT_PAGE_SIZE + 2)
    target = posted[0]

    unfiltered = mock_platform.result_page(mock_platform.results_url(created))
    assert len(set(result_users(unfiltered.results))) > 1, (
        f"The unfiltered results container carries {result_users(unfiltered.results)}, which is "
        "not more than one student — so a relation URL that had lost the filter would answer with "
        "the same results as one that kept it, and this test could not see the defect it is named "
        "for."
    )

    filtered = mock_platform.result_page(
        mock_platform.with_query(mock_platform.results_url(created), {"user_id": target})
    )
    assert result_users(filtered.results) == [target], (
        f"Asking the results container for `user_id={target}` returned "
        f"{result_users(filtered.results)}. The filter is accepted and ignored, so a tool asking "
        "for one student is handed the class."
    )
    assert filtered.relations, (
        f"The filtered results container advertises no `Link` relations at all (header "
        f"{filtered.link_header!r}), so there is no advertised URL for this test to follow. E0-28 "
        "item 5 puts `first`, `last` and `current` on a container that fits on one page, and "
        "without them the assertion below asserts nothing."
    )
    for relation, advertised in sorted(filtered.relations.items()):
        page = mock_platform.result_page(urljoin(filtered.url, advertised))
        assert result_users(page.results) == [target], (
            f"The `{relation}` relation of the container filtered by `user_id={target}` points at "
            f"`{advertised}`, which answers with {result_users(page.results)}. The filter reached "
            "the page and not the URL the platform advertises about itself, so a tool following "
            "its own platform's link is handed results it did not ask for."
        )


# ---------------------------------------------------------------------------
# Item 5 — the relations a single-page container still carries.
# ---------------------------------------------------------------------------


def test_a_single_page_roster_advertises_first_last_and_current_and_no_next(
    mock_platform: Any,
) -> None:
    """Item 5: a container that fits on one page still says so with a `Link` header.

    **The mutation is `link_header` returning `None` for a single page**, which
    is what it does today. It is right about `next` and under-realistic about the
    rest: Canvas, Moodle and D2L all send `first`, `last` and `current` on a
    one-page container, so a client written against "read `last` to learn the
    extent" — which is how a tool sizes a sync before it starts — finds nothing
    here and has to guess.

    **The near miss is the opposite defect and it is the more expensive one**: a
    header that advertises `next` whenever the page it is on is full. The seeded
    five-member section is the fixture that catches it, which is what that
    section exists for, and it is why "a single page" is defined here as *a page
    holding every member the container has* rather than as "a walk that returned
    one page". Under that mutation the walk returns two pages, the second empty,
    and a test defined the other way would report no single-page container to
    look at rather than the defect.

    `prev` is required absent for the same reason as `next`: page one has no
    predecessor, and a client that follows one arrives back where it started.
    """
    walked = walked_rosters(mock_platform)
    single = [
        (context, pages)
        for context, pages in walked
        if pages and len(pages[0].members) == sum(len(page.members) for page in pages)
    ]
    assert single, (
        "No seeded roster holds every one of its members on its first page: "
        + "; ".join(
            f"{context.context_id}: {[len(page.members) for page in pages]}"
            for context, pages in walked
            if pages
        )
        + ". E0-15 seeds a five-member section precisely so a container that fits on one page "
        "exists to ask this of, and a roster that spilled over is a seed that has changed size."
    )
    for context, pages in single:
        page = pages[0]
        missing = [
            relation for relation in ("first", "last", "current") if relation not in page.relations
        ]
        assert not missing, (
            f"The single-page roster for {context.context_id} carries {sorted(page.relations)} and "
            f"is missing {missing} — its Link header is {page.link_header!r}. E0-28 item 5: a "
            "single-page container carries the relations that do apply. A client reading `last` to "
            "learn how big a sync will be finds nothing here and has to guess."
        )
        assert "next" not in page.relations, (
            f"The single-page roster for {context.context_id} advertises a next page at "
            f"`{page.relations['next']}` while holding every member it has ({len(page.members)}). "
            "That is a header advertising a page that does not exist — the most common paging "
            "defect there is, and the one this section's size exists to catch."
        )
        assert "prev" not in page.relations, (
            f"The first page of the roster for {context.context_id} advertises a previous page at "
            f"`{page.relations['prev']}`. Page one has no predecessor, and a client that follows "
            "one arrives back where it started."
        )


def test_every_page_of_a_multi_page_roster_advertises_itself_as_current(
    mock_platform: Any,
) -> None:
    """Item 5 on the pages of a container that really does page.

    `current` is the relation a client uses to say where it is — a resumable sync
    records it and starts again there — so a `current` that points at the first
    page from every page, or at the next one, is worse than an absent relation:
    the resume lands somewhere plausible and wrong. It is asserted by *following*
    it and comparing the members, because two URLs that differ in spelling may be
    the same page and two that look alike may not be.

    **`next` is deliberately not asserted here**, and the reason is worth saying:
    the walk stops when a page advertises no `next`, so "the last page has none"
    and "every earlier page has one" are both true of any walk by construction —
    a test asserting them would pass against any implementation, which is
    `docs/MISTAKES.md` entry 3 in its purest form. Where a wrong `next` is
    observable is the single-page test above and
    `test_no_page_of_a_walked_roster_comes_back_empty` in the roster suite.
    """
    walked = walked_rosters(mock_platform)
    paged = [(context, pages) for context, pages in walked if len(pages) > 1]
    assert paged, (
        "No seeded roster came back on more than one page, so there is no page after the first "
        "for this test to ask about. E0-15 criterion 2 requires a roster larger than one page; "
        f"{[(context.context_id, len(pages)) for context, pages in walked]}."
    )
    for context, pages in paged:
        for ordinal, page in enumerate(pages, start=1):
            for relation in ("first", "last", "current"):
                assert relation in page.relations, (
                    f"Page {ordinal} of the roster for {context.context_id} carries "
                    f"{sorted(page.relations)} and no `{relation}` — its Link header is "
                    f"{page.link_header!r}. E0-28 item 5 puts `first`, `last` and `current` on "
                    "every page, which is the set Canvas sends."
                )
            here = mock_platform.membership_page(urljoin(page.url, page.relations["current"]))
            assert member_ids(here) == member_ids(page), (
                f"Page {ordinal} of the roster for {context.context_id} advertises itself as "
                f"`{page.relations['current']}`, and fetching that URL returns "
                f"{member_ids(here)} where the page holds {member_ids(page)}. A `current` that "
                "points anywhere but at the page that sent it makes a resumable sync resume in "
                "the wrong place — plausibly, and silently."
            )
            if ordinal == 1:
                assert "prev" not in page.relations, (
                    f"Page 1 of the roster for {context.context_id} advertises a previous page at "
                    f"`{page.relations['prev']}`."
                )
            else:
                assert "prev" in page.relations, (
                    f"Page {ordinal} of the roster for {context.context_id} carries no `prev` "
                    f"relation ({sorted(page.relations)}). A client that has paged forward and "
                    "wants to step back has nothing to follow."
                )


# ---------------------------------------------------------------------------
# Item 9 — a `userId` containing a slash routes, and does not collide.
# ---------------------------------------------------------------------------


def test_a_score_posted_for_a_user_id_containing_a_slash_round_trips_through_its_result_url(
    mock_platform: Any,
    signed_launch: Any,
) -> None:
    """Item 9: the platform serves the `resultUrl` it composed.

    **The mutation is the platform as it stands, measured rather than imagined.**
    `result_url` percent-encodes the identifier with `safe=''`, so a score posted
    for `a/b` answers 200 with a `resultUrl` of `…/results/a%2Fb` — and a `GET` of
    that URL is Starlette's own 404, because ASGI hands the router the *decoded*
    path and the default converter stops at a slash. The platform composes a URL
    it does not serve, which is precisely the hazard a per-user result route
    exists to close.

    E0-28 rejects the alternative — refusing such a `userId` at the score post —
    because that narrows AGS, which types `userId` as a string and says nothing
    about its characters, and because a `sub` is the platform's own value: a tool
    cannot choose it and has no way to avoid one.

    Rare today, when every seeded `sub` is a UUID, and not rare in the sector: a
    platform that keys users on an LDAP distinguished name or a path-shaped
    external id issues these routinely.
    """
    created = mock_platform.create_line_item(signed_launch)
    response = accepted_score(mock_platform, created, SLASHED_USER_ID)

    body = response.json()
    assert isinstance(body, dict) and body.get("resultUrl"), (
        f"The Score service answered {response.status_code} with body {response.text[:200]!r} for "
        f"a `userId` of {SLASHED_USER_ID!r}, and it carries no `resultUrl`. AGS returns it so a "
        "tool can read back the result it just caused."
    )
    read = mock_platform.service_get(str(body["resultUrl"]))
    assert read.status_code == 200, (
        f"The `resultUrl` the platform composed for {SLASHED_USER_ID!r} — `{body['resultUrl']}` — "
        f"answered {read.status_code}. A URL a platform hands out and does not serve is a lie "
        "that only surfaces in whichever job follows the link, and here it is the platform's own "
        "encoding of its own identifier that it cannot route back."
    )
    assert str(read.json().get("userId", "")) == SLASHED_USER_ID, (
        f"`{body['resultUrl']}` answered {read.json()!r}, which is not {SLASHED_USER_ID!r}'s "
        "result. A route that answers 200 with somebody else's grade is worse than one that 404s."
    )


def test_the_result_for_a_slashed_user_id_identifies_itself_with_the_url_that_answers(
    mock_platform: Any,
    signed_launch: Any,
) -> None:
    """Item 9's second surface: the `Result` in the container carries the same routable id.

    The `resultUrl` on the Score response and the `id` inside the container are
    composed by the same helper and read by different clients — a passback follows
    the first, a reconciliation follows the second — so a fix that reached only
    one of them leaves half the defect in place. That is `docs/MISTAKES.md` entry
    13, and it is the mutation this test kills: repair the route and keep an
    `id` composed some other way, and the container goes on advertising a dead
    URL while the Score response works.

    The container is required to carry the result first, so that "the id answers"
    is a fact about a result that exists rather than about a loop over nothing.
    """
    created = mock_platform.create_line_item(signed_launch)
    posted = accepted_score(mock_platform, created, SLASHED_USER_ID)

    matching = [
        result
        for result in mock_platform.results(created)
        if str(result.get("userId", "")) == SLASHED_USER_ID
    ]
    assert len(matching) == 1, (
        f"The results container reports {len(matching)} results for {SLASHED_USER_ID!r} after one "
        f"score was posted: {mock_platform.results(created)!r}."
    )
    identifier = str(matching[0].get("id"))
    assert identifier == str(posted.json().get("resultUrl")), (
        f"The result in the container identifies itself as `{identifier}` and the Score response "
        f"handed back `{posted.json().get('resultUrl')}`. Two spellings of one result's URL means "
        "a tool that stored one cannot recognise the other, and only one of them is being tested "
        "by whichever test happens to follow it."
    )
    read = mock_platform.service_get(identifier)
    assert read.status_code == 200, (
        f"The result for {SLASHED_USER_ID!r} identifies itself as `{identifier}` and that URL "
        f"answered {read.status_code}. AGS makes a result's `id` the URL it lives at."
    )


def test_a_literally_encoded_user_id_is_a_different_student_from_the_slashed_one(
    mock_platform: Any,
    signed_launch: Any,
) -> None:
    """The near miss on item 9: two students whose identifiers must not collide.

    A `:path` converter opens a route that a slash can reach, and the obvious way
    to get there is to decode the identifier somewhere it was already decoded.
    Do that and `a%2Fb` — a perfectly ordinary identifier that happens to *look*
    like an encoding — becomes `a/b`, and two students share one result. That is
    the failure this pair exists for, and it is worse than the 404 it replaces:
    one student's participation grade is served to a job asking about the other,
    and neither side has any way to notice.

    Asserted in three places, because the collision can land in any of them: the
    two `resultUrl`s the platform composes must differ, the container must carry
    two results rather than one, and each URL must answer with its own student.
    """
    created = mock_platform.create_line_item(signed_launch)
    slashed = accepted_score(mock_platform, created, SLASHED_USER_ID)
    literal = accepted_score(mock_platform, created, LITERALLY_ENCODED_USER_ID)

    urls = {
        SLASHED_USER_ID: str(slashed.json().get("resultUrl")),
        LITERALLY_ENCODED_USER_ID: str(literal.json().get("resultUrl")),
    }
    assert urls[SLASHED_USER_ID] != urls[LITERALLY_ENCODED_USER_ID], (
        f"The platform composed one URL — `{urls[SLASHED_USER_ID]}` — for both "
        f"{SLASHED_USER_ID!r} and {LITERALLY_ENCODED_USER_ID!r}. They are two different `sub` "
        "values, so one result URL for both is one student's grade standing in for another's."
    )

    served = result_users(mock_platform.results(created))
    assert sorted(served) == sorted((SLASHED_USER_ID, LITERALLY_ENCODED_USER_ID)), (
        f"Scores were posted for {SLASHED_USER_ID!r} and {LITERALLY_ENCODED_USER_ID!r} and the "
        f"results container carries {served}. A fold that decodes an identifier it was given "
        "already decoded merges the two into one student."
    )

    for user_id, url in urls.items():
        read = mock_platform.service_get(url)
        assert (
            read.status_code == 200
        ), f"The `resultUrl` for {user_id!r} — `{url}` — answered {read.status_code}."
        assert str(read.json().get("userId", "")) == user_id, (
            f"`{url}` was composed for {user_id!r} and answers with "
            f"{read.json().get('userId')!r}. A route that decodes once too often serves one "
            "student's grade to a request about the other, and answers 200 doing it."
        )


# ---------------------------------------------------------------------------
# Item 10 — the caps, which are numbers no test named.
# ---------------------------------------------------------------------------


def test_the_line_item_container_serves_its_cap_and_advertises_the_rest(
    mock_platform: Any,
    signed_launch: Any,
    link_relations_in: Any,
) -> None:
    """Item 10, on the container that already clamps. **Born green.**

    **The mutations, and both were measured on this container during E0-15's
    third fix round.** Removing `min(limit, MAX_LINE_ITEM_LIMIT)` left every test
    in the repository green, so a tool asking for a million line items is served
    a million in one response where Canvas would cap and page. And moving the cap
    by one is invisible to anything that does not name the number — which is the
    ticket's actual complaint: "the line-item cap is a number no test names".

    So the number is written into this file rather than imported from
    `mock-lms/app/ags.py` (`docs/MISTAKES.md` entry 19). An import would move
    with the constant and stay green through exactly the change this test exists
    to catch.

    **Why `next` is asserted beside the count**: a clamp that serves the cap and
    advertises nothing is a truncation, and it is the worse of the two failures.
    A tool that asked for everything, received a hundred, and was told nothing
    more exists has a hundred grades and no reason to ask again.

    The container is filled by POST rather than by the seed, which E0-28 item 10
    requires — the seed stays small, and a fixture over the cap belongs to the
    test that needs one.
    """
    for _ in range(MAX_LINE_ITEM_LIMIT + 1):
        mock_platform.create_line_item(signed_launch)

    url = mock_platform.with_query(
        mock_platform.line_items_url(signed_launch), {"limit": OVER_LARGE_LIMIT}
    )
    response = mock_platform.service_get(url, accept=LINE_ITEM_CONTAINER_MEDIA_TYPE)
    assert response.status_code == 200, (
        f"Asking the line-item container for `limit={OVER_LARGE_LIMIT}` answered "
        f"{response.status_code}. Body begins {response.text[:200]!r}. The rule is to clamp and "
        "serve a page: a tool cannot discover the cap, so refusing leaves it guessing."
    )
    served = mock_platform.line_items_of(response)
    assert len(served) == MAX_LINE_ITEM_LIMIT, (
        f"A context holding more than {MAX_LINE_ITEM_LIMIT} line items, asked for "
        f"{OVER_LARGE_LIMIT}, served {len(served)}. E0-28 item 10: the container serves its cap "
        f"and advertises the rest. {MAX_LINE_ITEM_LIMIT} is `MAX_LINE_ITEM_LIMIT`'s value, "
        "written here rather than imported so that moving the constant moves this assertion "
        "instead of moving with it."
    )
    relations = link_relations_in(response.headers.get("link"))
    assert relations.get("next"), (
        f"The clamped page carries {sorted(relations)} and advertises no next page (Link header "
        f"{response.headers.get('link')!r}), while the context holds more than "
        f"{MAX_LINE_ITEM_LIMIT} line items. A clamp that does not advertise the remainder is a "
        "silent truncation: the tool asked for everything and has no reason to ask again."
    )


def test_the_results_container_serves_its_cap_and_advertises_the_rest(
    mock_platform: Any,
    signed_launch: Any,
) -> None:
    """Item 10's mirror on the surface item 4 builds.

    **The mutation is shipping the new container with the debt the old one had.**
    A results endpoint that pages but takes any `limit` it is given is one
    request away from serving an institution's whole gradebook, and nothing in
    item 4's tests can see it — they ask for two and for nothing, never for more
    than exists. This is the assertion that makes `MAX_RESULT_LIMIT` a number the
    suite names, on the same terms as the line-item cap above: the value is
    written here rather than imported, so moving the constant is loud.

    The near miss is a cap off by one — 99 or 101 served — which is why the count
    is exact rather than "no more than the cap".
    """
    created = mock_platform.create_line_item(signed_launch)
    many_scored_users(mock_platform, created, MAX_RESULT_LIMIT + 1)

    page = mock_platform.result_page(
        mock_platform.with_query(mock_platform.results_url(created), {"limit": OVER_LARGE_LIMIT})
    )
    assert len(page.results) == MAX_RESULT_LIMIT, (
        f"A line item holding {MAX_RESULT_LIMIT + 1} results, asked for {OVER_LARGE_LIMIT}, served "
        f"{len(page.results)}. E0-28 item 10: a container over its cap serves the cap. "
        f"{MAX_RESULT_LIMIT} is `MAX_RESULT_LIMIT`'s value, written here rather than imported so "
        "that moving the constant moves this assertion instead of moving with it."
    )
    assert page.relations.get("next"), (
        f"The clamped results page carries {sorted(page.relations)} and advertises no next page "
        f"(Link header {page.link_header!r}), while the line item holds "
        f"{MAX_RESULT_LIMIT + 1} results. A tool that asked for everything, received "
        f"{MAX_RESULT_LIMIT} and was told nothing more exists has an institution's grades minus "
        "one and no reason to ask again."
    )
