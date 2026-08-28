"""The mock platform's roster service, walked the way a roster sync walks it — E0-15.

E0-15 builds the *platform* side of Names and Role Provisioning Service 2.0: a
paged course roster whose members carry roles and enrollment status. Everything
below asserts what the platform produces, driven through the URL the launch
advertised rather than through a path this file invented.

**How a test finds the service.** In LTI Advantage the platform announces its
services inside the launch it has just signed — the NRPS claim carries the
context memberships URL — so a test that discovers the endpoint that way is
doing what E1's sync will do, and is not inventing an interface E0-15 left open.
Nothing here knows a path. A mock serving a perfectly good roster at a fixed URL
with no claim in the token fails the first test in this module, which is the
right failure: `pylti1p3` (SPEC §7.1) would never find it.

**What is deliberately not here.** Tool-side roster sync — enrollment
provisioning, the hourly schedule, debouncing on launch — is E1's, and E0-15's
out-of-scope list says so. There is no test below of what Pulse does with a
roster.

**Nor is there a test of the access-token flow, and that sentence changed
meaning.** It used to mean there was none to test: E0-15 mentioned no grant and
E0-14 built none, so this suite called the services unauthenticated and a 401 was
reported as a gap in the ticket. E1-06 built the grant and E1-11's fix round made
this route require it, so every roster read below now carries a token the mock's
own endpoint issued — attached by `MockPlatform.roster_get`, which is why no test
here mentions one. What the route must **refuse** is a subject of its own and
lives in `test_mock_lms_nrps_requires_a_token.py`; a 401 reaching this module is
still a diagnosis rather than an assertion, because every test here is about what
a roster carries.

**No §4.1 invariant lives here.** The mock is a platform, not a Pulse read path;
the confidentiality invariants attach to what Pulse shows a human. What the
suite does assert about the seeded people — that their identities are obviously
fake — is in `test_mock_lms_seed_data.py`, where the seed is the subject.

**On "no member is duplicated or dropped".** Those are two different claims and
only one of them is checkable from the pages alone. Duplication is: the pages of
a container partition its membership, so the members counted across pages and
the members counted once have to be the same number.

A *drop* has no total to check against — NRPS containers carry no count — and
this suite reached for a lower bound first: every user the launch page will sign
a launch for is demonstrably a member of that context and has to appear in its
roster. A reviewer measured that as too weak to be worth much. Both launch users
sit at the head of every roster, so slicing one member off each page boundary
left the whole suite green. The claim now rests on the seed's own numbering
instead — a student identifier carries a trailing ordinal, and an assembled
roster whose ordinals have a hole has lost somebody — with the lower bound kept
beside it, because the two fail for different reasons and a reader is better off
seeing which. What neither reaches is a member lost from the very end of the
last page: nothing on this surface says how many there should have been.
"""

import re
from typing import Any
from urllib.parse import urlsplit

import pytest

pytestmark = pytest.mark.lti

# `mock_platform`, `link_relations_in` and the platform's service helpers come
# from `tests/fixtures/lti_services.py` and are reached through fixtures rather
# than imported. A test module that imports a fixtures module by name depends on
# where pytest happened to put `tests/` on `sys.path`, and an import error is
# not a red — it is a broken suite that reports nothing about the ticket.

# The three values NRPS 2.0 gives a membership `status`. Not this suite's
# choice: `pylti1p3` and every platform adapter compare against these exact
# strings, and SPEC §3.4 needs the difference between them — "Drops: scores stop
# updating" is a decision a tool can only make if the roster says a member is no
# longer active.
NRPS_MEMBERSHIP_STATUSES = ("Active", "Inactive", "Deleted")

# The member's identifier, spelled as NRPS 2.0 spells it. A container that
# spells it `userId` is one `pylti1p3` reads as a member with no user, so the
# strictness is the specification's rather than this suite's.
MEMBER_ID = "user_id"

# A `Link` header this suite builds itself, to check the parser the walk uses.
# Two entries, one of them carrying two relations on one URL, because that is
# the shape a substring search for "next" gets right for the wrong reason.
SAMPLE_LINK_HEADER = '<https://platform.invalid/memberships?page=2>; rel="next", '
SAMPLE_LINK_HEADER += '<https://platform.invalid/memberships?page=9>; rel="last first"'

# A member identifier ending in a number, split into the stem it shares with its
# classmates and that number. **This is the one place this suite reads a
# convention of the seed rather than of a specification**, and it is deliberate:
# see `test_an_assembled_roster_has_no_hole_where_a_page_boundary_was` for what
# it buys and what it costs. Nothing here says what the stem must be, how wide
# the number is, or how many there are — only that identifiers sharing a stem
# and a width are numbered without gaps.
NUMBERED_IDENTIFIER = re.compile(r"^(?P<stem>.*?)(?P<ordinal>\d+)$")

# How many members a numbered family needs before its numbering is treated as
# evidence. **This suite's choice.** Two identifiers ending in 1 and 2 are as
# likely to be a coincidence as a sequence, and a family of two is contiguous
# whatever a page boundary did to it.
SMALLEST_TELLING_FAMILY = 3


def roster_of(platform: Any, context: Any) -> list[Any]:
    """Every page of one context's roster, first to last."""
    return platform.membership_pages(context.memberships_url)


def walked_rosters(platform: Any) -> list[tuple[Any, list[Any]]]:
    """Every seeded context paired with its fully walked roster.

    Fails rather than answering an empty list, because every assertion below is
    over the members it returns and an empty walk satisfies most of them
    (`docs/MISTAKES.md` entry 3).
    """
    contexts = platform.seeded_contexts()
    assert contexts, (
        "The launch page offers no launches, so this suite found no context to fetch a roster "
        "for. E0-14 seeds the launches and E0-15 seeds the roster behind them."
    )
    return [(context, roster_of(platform, context)) for context in contexts]


def members_across(pages: list[Any]) -> list[dict[str, Any]]:
    """Every member on every page of one walked roster, in page order."""
    return [member for page in pages for member in page.members]


def numbered_families(members: list[dict[str, Any]]) -> dict[tuple[str, int], list[int]]:
    """Member identifiers grouped by the stem and width they are numbered within.

    A family is every identifier sharing an exact stem *and* an exact digit
    width, so `…-student-01` and `…-student-02` are one family while an
    instructor's identifier, or a student of another section, is not in it. That
    is what keeps the numbering evidence about one sequence rather than about
    whatever else happens to end in a digit.
    """
    families: dict[tuple[str, int], list[int]] = {}
    for member in members:
        matched = NUMBERED_IDENTIFIER.match(str(member.get(MEMBER_ID, "")))
        if matched:
            digits = matched.group("ordinal")
            families.setdefault((matched.group("stem"), len(digits)), []).append(int(digits))
    return families


def every_member(walked: list[tuple[Any, list[Any]]]) -> list[dict[str, Any]]:
    """Every member of every seeded context, with a guard against emptiness."""
    members = [member for _, pages in walked for member in members_across(pages)]
    assert members, (
        "Every seeded roster came back with no members at all, so every assertion about what a "
        "member carries would hold vacuously. E0-15 seeds 'students, instructors, and "
        "enrollments'."
    )
    return members


# ---------------------------------------------------------------------------
# Finding the service at all, and what it answers with.
# ---------------------------------------------------------------------------


def test_a_launch_advertises_the_names_and_role_provisioning_service(
    signed_launch: Any,
    mock_platform: Any,
) -> None:
    """The claim a tool discovers the roster through, carrying an absolute URL.

    Catches the mock that serves a good roster at `/nrps/...` and puts nothing in
    the token. Every other test in this module would then be written against a
    path someone chose, E1's sync would be written the same way, and the first
    real platform — which publishes a different path per context — would have no
    route in at all.

    The URL is required to be absolute for the same reason and it is a separate
    failure: a claim carrying `/nrps/context/1/memberships` looks correct in a
    body and cannot be resolved by a tool that received the token over a queue,
    out of a session, or from anywhere but the response it arrived in.
    """
    url = mock_platform.memberships_url(signed_launch)
    split = urlsplit(url)
    assert split.scheme and split.netloc, (
        f"The NRPS claim advertises `{url}`, which is not an absolute URL. A tool resolves this "
        "value with no knowledge of where the token came from, so a relative path is a service "
        "it cannot call."
    )


def test_the_membership_service_answers_a_container_naming_its_context(
    mock_platform: Any,
    signed_launch: Any,
) -> None:
    """The container shape, before anything reads members out of it.

    Catches the two shapes a mock produces when nobody checks: a bare JSON array
    of members, and an object whose `members` key is missing because the
    serialiser named it `memberships`. Both are readable by hand and neither is
    readable by `pylti1p3`, which asks the container for its `members`.

    `context` is asserted because it is what ties a roster to a section. A
    container that answers the same membership for every URL passes every other
    test in this module — the members are all there, the paging is right — and
    gives E1 one roster for the whole institution.
    """
    page = mock_platform.membership_page(mock_platform.memberships_url(signed_launch))
    context = page.document.get("context")
    assert isinstance(context, dict) and context.get("id"), (
        f"The membership container carries no `context` object with an `id` (it carries "
        f"{sorted(page.document)}). NRPS 2.0 puts the context there, and it is what says which "
        "section this roster belongs to."
    )
    assert isinstance(page.document.get("members"), list), (
        f"The membership container carries no `members` array (it carries "
        f"{sorted(page.document)}). That member is the roster; a container without it is a "
        "document `pylti1p3` reads as an empty class."
    )


def test_the_membership_container_names_the_context_the_launch_came_from(
    mock_platform: Any,
) -> None:
    """The roster a launch points at *declares* that section. Only the declaration.

    Catches a memberships URL built without the context in it, and a container
    that names whichever context it happened to serve last.

    **What it does not reach, corrected after it was measured.** This docstring
    used to claim it caught "a handler that ignores the context it was given and
    answers the first seeded section". It does not: the mutation that serves
    every section the first section's *members* leaves the declared `context.id`
    exactly as it was, so this test compares the two values it was given and
    passes. `test_two_seeded_contexts_do_not_return_the_same_membership` below is
    the one that reaches the membership, and the pair is what the claim needs —
    a container may agree with itself about which section it is describing while
    describing somebody else's class.
    """
    for context in mock_platform.seeded_contexts():
        page = mock_platform.membership_page(context.memberships_url)
        served = page.document.get("context")
        served_id = served.get("id") if isinstance(served, dict) else None
        assert served_id == context.context_id, (
            f"The roster at `{context.memberships_url}` names context {served_id!r}, and the "
            f"launch that advertised that URL carries context {context.context_id!r}. A roster "
            "service that answers the same context whatever it is asked for gives E1 one class "
            "list for the whole institution."
        )


def test_two_seeded_contexts_do_not_return_the_same_membership(mock_platform: Any) -> None:
    """The roster a context serves is that context's, asserted on the members.

    **The mutation this exists to kill, which was run rather than imagined.** In
    `mock-lms/app/nrps.py`, `membership_page` reads
    `platform.enrollments_in(context.context_id)`; changed to
    `platform.enrollments_in(platform.contexts[0].context_id)`, every section
    served the first section's roster and all 61 tests then in the four
    mock-platform modules stayed green. Every other assertion in this module is
    satisfied by the wrong class list: the container still declares the context
    it was asked for, the pages still divide and still carry no duplicate, the
    members still carry roles and statuses, and every launchable user still
    turns up — because the seed enrolls the launch users in every section, so
    the lower bound in `every_user_the_platform_will_launch_appears_in_the_
    roster_of_its_context` is met by the wrong roster too. E1's sync would write
    one section's enrollments into every section, and E3 would grade students
    for courses they are not in.

    **What this does not reach**, and it is a wide gap said plainly rather than
    softened. It asserts only that the service *distinguishes* contexts, not
    that any roster is the right one: two contexts whose rosters were swapped
    pass this, and so does a service that derives membership from a path segment
    that is not the context. Naming the seed's own section codes or member
    counts as expected values would close that and would make this test a second
    copy of the seed, which goes stale the first time a section is added; the
    ticket asks for a roster per context, not for a particular roster, so this
    is the strongest form that stays inside it.

    Both guards are load-bearing rather than ceremony. A seed with one section
    makes the comparison vacuous — there is no second roster for the first to
    differ from — and a service answering every context an empty membership
    makes every roster equal, which is this assertion failing for a reason that
    has nothing to do with the mutation, so it is reported as itself.
    """
    walked = walked_rosters(mock_platform)
    assert len(walked) > 1, (
        f"The platform seeds one context ({[context.context_id for context, _ in walked]}), so "
        "there is no second roster for the first to differ from and this test cannot see a "
        "service that serves one section's members for every section. E0-15 seeds 'a handful of "
        "courses and sections'."
    )
    memberships = {
        context.context_id: {str(member.get(MEMBER_ID)) for member in members_across(pages)}
        for context, pages in walked
    }
    empty = sorted(name for name, members in memberships.items() if not members)
    assert not empty, (
        f"{len(empty)} seeded contexts returned no members at all ({empty}), and every empty "
        "roster equals every other one — so the comparison below would fail for a reason that has "
        "nothing to do with which context was asked for."
    )
    assert len({frozenset(members) for members in memberships.values()}) > 1, (
        "Every seeded context returns the same membership: "
        + "; ".join(f"{name}: {sorted(members)}" for name, members in sorted(memberships.items()))
        + ". A roster service that answers one section's enrollments whatever it is asked for "
        "declares the right context and serves the wrong class, which is what E1's sync would "
        "write into every section."
    )


# ---------------------------------------------------------------------------
# Criterion 1 — members carry role and enrollment status.
# ---------------------------------------------------------------------------


def test_every_roster_member_carries_at_least_one_role(mock_platform: Any) -> None:
    """Criterion 1, the role half.

    Catches a roster of names and identifiers with no roles at all — the shape a
    mock takes when the seed is written as a list of people rather than as a list
    of enrollments — and catches `roles` serialised as a bare string, which is
    what a single-role member becomes when nobody wraps it. A tool reading
    `"Learner"` as a list finds eight roles of one character each.

    Whether a role is spelled as an LIS vocabulary URI or by its short name is
    deliberately not asserted: NRPS 2.0's own example uses short names while the
    launch's roles claim requires URIs, so a rule here would be this suite
    inventing conformance the ticket does not state.
    """
    roleless = [
        member
        for member in every_member(walked_rosters(mock_platform))
        if not (
            isinstance(member.get("roles"), list)
            and member["roles"]
            and all(isinstance(role, str) and role for role in member["roles"])
        )
    ]
    assert not roleless, (
        f"{len(roleless)} roster members carry no usable `roles` array — the first is "
        f"{roleless[0]!r}. E0-15 criterion 1: 'NRPS returns a roster whose members carry role and "
        "enrollment status.' A member with no role cannot be turned into an enrollment, and a "
        "`roles` that is a bare string is read character by character."
    )


def test_every_roster_member_carries_an_enrollment_status(mock_platform: Any) -> None:
    """Criterion 1, the status half, against NRPS 2.0's three values.

    Catches a status omitted (every member reads as active, and SPEC §3.4's
    "Drops: scores stop updating" has nothing to fire on), and a status invented
    — `"enrolled"`, `"dropped"`, `"active"` in lower case. Each of those is
    perfectly readable and none is a value any platform sends, so E1's ingestion
    would be written against a vocabulary that exists nowhere but this mock.
    """
    members = every_member(walked_rosters(mock_platform))
    wrong = [member for member in members if member.get("status") not in NRPS_MEMBERSHIP_STATUSES]
    assert not wrong, (
        f"{len(wrong)} of {len(members)} roster members carry a `status` outside "
        f"{list(NRPS_MEMBERSHIP_STATUSES)} — the first is {wrong[0].get('status')!r} on "
        f"{wrong[0]!r}. E0-15 criterion 1 asks for enrollment status on every member, and NRPS "
        "2.0 fixes those three spellings; anything else is a vocabulary only this mock has."
    )


def test_every_roster_member_is_identified_the_way_a_launch_identifies_a_user(
    mock_platform: Any,
) -> None:
    """`user_id` on the member, spelled as NRPS spells it.

    The precondition for every test below that matches a member against a
    launch, asserted on its own so that a container spelling it `userId` or `id`
    reports as one failure naming the field rather than as three failures that
    look like members going missing.
    """
    members = every_member(walked_rosters(mock_platform))
    unnamed = [member for member in members if not isinstance(member.get(MEMBER_ID), str)]
    assert not unnamed, (
        f"{len(unnamed)} of {len(members)} roster members carry no `{MEMBER_ID}` string — the "
        f"first carries {sorted(unnamed[0])}. NRPS 2.0 spells it `{MEMBER_ID}`, and it is the "
        "value SPEC §4 keys every response to: the LMS user ID a launch carries as `sub`."
    )


# ---------------------------------------------------------------------------
# Criterion 2 and the definition of done — paging.
# ---------------------------------------------------------------------------


def test_the_link_header_parser_reads_a_next_relation_and_ignores_the_others(
    link_relations_in: Any,
) -> None:
    """The control on the walk, run before the walk's answers are believed.

    `docs/MISTAKES.md` entry 3: a pattern searched against text is "a test that
    passed for a reason unrelated to what it asserted" wearing a disguise, so it
    is run against the text it is claimed to catch *and* the text it is claimed
    to allow. Both halves are here, and neither is ceremony — a parser that
    returned `{}` for everything would make the walk stop after one page, which
    silently turns every paging assertion below into a statement about page one.
    """
    relations = link_relations_in(SAMPLE_LINK_HEADER)
    assert relations.get("next") == "https://platform.invalid/memberships?page=2"
    assert relations.get("last") == "https://platform.invalid/memberships?page=9"
    assert relations.get("first") == "https://platform.invalid/memberships?page=9"
    assert link_relations_in('<https://platform.invalid/m?page=9>; rel="prev"').get("next") is None
    assert link_relations_in(None) == {}
    assert link_relations_in("") == {}


def test_a_roster_larger_than_one_page_advertises_the_next_page_in_a_link_header(
    mock_platform: Any,
) -> None:
    """Criterion 2, and the reason E0-15 seeds more members than fit on a page.

    Two mutations, and the second is the near miss. The first is a mock that
    answers the whole roster in one response: every other test here passes,
    paging is never exercised, and §7.3's named per-platform deviation — "NRPS
    paging" — is a bug class E1 meets for the first time against a real LMS.

    The second is a mock that pages the *body* and carries the next URL inside
    the JSON rather than in a `Link` header. A test walking the body would call
    that correct. A conformant tool reads the header, sees no next relation, and
    silently syncs one page of the class — which looks exactly like a small
    section rather than like a defect.
    """
    walked = walked_rosters(mock_platform)
    paged = [
        (context, pages) for context, pages in walked if pages and pages[0].relations.get("next")
    ]
    assert paged, (
        "No seeded roster's first page carries a `Link` header with a `rel=next` relation. "
        + "; ".join(
            f"{context.context_id}: {len(members_across(pages))} members over {len(pages)} "
            f"page(s), first page Link header {pages[0].link_header!r}"
            for context, pages in walked
            if pages
        )
        + ". E0-15 criterion 2: 'A roster larger than one page returns `Link` headers and a test "
        "walks all pages to assemble the full membership.' A next URL carried in the body instead "
        "leaves a conformant tool syncing page one and calling it the class."
    )
    context, pages = paged[0]
    assert len(pages[0].members) < len(members_across(pages)), (
        f"The roster for {context.context_id} advertises a next page and its first page already "
        "holds every member, so the header points at nothing new. Paging that does not divide "
        "the roster is a header a tool follows for no reason."
    )


def test_walking_every_page_of_a_roster_returns_each_member_exactly_once(
    mock_platform: Any,
) -> None:
    """The definition of done's "no member is duplicated", from the pages themselves.

    The pages of a container partition its membership, so counting members across
    the pages and counting them once has to give the same number. Catches the
    off-by-one that overlaps pages — an offset advanced by one less than the page
    size, or a next URL that repeats the offset it was served at — which duplicates
    a member per page boundary. E3 divides valid weeks by weeks elapsed per
    student; a student who appears twice in a synced roster is either two students
    or one whose enrollment window is written twice.

    The guard above the assertion is not ceremony: over a roster that fits on one
    page the comparison is `n == n` for any implementation at all, so a mock that
    stopped paging would satisfy this test rather than fail it.
    """
    walked = walked_rosters(mock_platform)
    paged = [(context, pages) for context, pages in walked if len(pages) > 1]
    assert paged, (
        "No seeded roster came back on more than one page, so this test would compare a page "
        "against itself. Criterion 2 requires a roster larger than one page; "
        f"{[(context.context_id, len(pages)) for context, pages in walked]}."
    )
    for context, pages in paged:
        members = members_across(pages)
        identifiers = [member.get(MEMBER_ID) for member in members]
        repeated = sorted({str(name) for name in identifiers if identifiers.count(name) > 1})
        assert not repeated, (
            f"Walking the {len(pages)} pages of the roster for {context.context_id} returned "
            f"{len(members)} members of whom {len(set(map(str, identifiers)))} are distinct; "
            f"{repeated} appear more than once. The pages of a membership container partition "
            "the membership, so a member on two pages is a paging offset that moves by less than "
            "the page it just served."
        )


def test_no_page_of_a_walked_roster_comes_back_empty(mock_platform: Any) -> None:
    """The other half of a wrong `Link` header: one that says next once too often.

    Catches the most common paging mistake there is — advertising a next page
    whenever the page just served was full — which produces a final page with no
    members on it. The membership is complete, no member is duplicated or
    dropped, and every test above passes. What it breaks is agreement about when
    to stop: a tool paging until the header goes quiet makes one more request
    than exists, and a tool paging until a short page disagrees with the header
    the platform sent.
    """
    for context, pages in walked_rosters(mock_platform):
        empty = [page for page in pages if not page.members]
        assert not empty, (
            f"The roster for {context.context_id} came back over {len(pages)} pages and "
            f"{len(empty)} of them carry no members — the first is `{empty[0].url}`, served with "
            f"Link header {empty[0].link_header!r}. A `Link` header that advertises a next page "
            "whenever the page it is on is full advertises one page too many."
        )


def test_an_assembled_roster_has_no_hole_where_a_page_boundary_was(
    mock_platform: Any,
) -> None:
    """The definition of done's "no member is dropped", from the seed's own numbering.

    **The mutation, which was run rather than imagined.** Slicing the page as
    `members[(page - 1) * PAGE_SIZE : page * PAGE_SIZE - 1]` loses the last
    member of every page and left the whole suite green. Nothing else sees it:
    the pages still carry no duplicate, every page is still non-empty, the
    container still names its context, and the lower bound below is still met
    because both launch users sit at the head of the roster. E1 would sync a
    class with one student missing per page, and E3 would never grade them —
    silently, since a short roster looks exactly like a small section.

    **What it rests on, said plainly because it is a dependence on the seed
    rather than on a specification.** A seeded student's identifier ends in a
    zero-padded ordinal, so an assembled roster is a sequence and a lost member
    is a hole in it. No specific stem, width, or count is written here — only
    that identifiers sharing a stem and a width run without gaps — but if the
    seed ever numbers its people differently this test goes red, and the message
    says so rather than leaving the next reader to guess whether a defect was
    found. It is the only ground truth on this surface: NRPS containers carry no
    total.

    **What it does not reach.** A member lost from the very end of the last page
    leaves a sequence with no hole in it, and nothing published anywhere says
    where the sequence should have stopped. The `starts at 1` assertion closes
    the mirror of that at the front, and is separated from the contiguity
    assertion because it is the one that would go red on a seed that numbered
    from zero — a convention this suite has no business fixing.
    """
    walked = walked_rosters(mock_platform)
    paged = {context.context_id for context, pages in walked if len(pages) > 1}
    assert paged, (
        "No seeded roster came back on more than one page, so no page boundary exists for a "
        "member to be lost at and this test cannot see the mutation it exists for. Criterion 2 "
        f"requires a roster larger than one page; {[(c.context_id, len(p)) for c, p in walked]}."
    )

    families = {
        (context.context_id, stem, width): sorted(ordinals)
        for context, pages in walked
        for (stem, width), ordinals in numbered_families(members_across(pages)).items()
        if len(ordinals) >= SMALLEST_TELLING_FAMILY
    }
    assert any(name in paged for name, _, _ in families), (
        "No section whose roster spans more than one page carries a family of at least "
        f"{SMALLEST_TELLING_FAMILY} member identifiers ending in a number, so there is no "
        "sequence to find a hole in. The families found were "
        f"{ {key: len(ordinals) for key, ordinals in families.items()} }. This test reads the "
        "seed's own numbering because a membership container publishes no total; if the seed "
        "has stopped numbering its students, the ticket needs another way to say how many "
        "members a roster should have."
    )

    for (name, stem, width), ordinals in sorted(families.items()):
        assert max(ordinals) - min(ordinals) + 1 == len(ordinals), (
            f"The assembled roster for {name} carries {len(ordinals)} identifiers numbered "
            f"`{stem}` at {width} digits, running {ordinals} — which has a hole in it. The "
            "pages of a membership container partition the membership, so a missing ordinal is a "
            "member the walk was never served: a page sliced one short of its own boundary, or an "
            "offset advanced past it."
        )
        assert min(ordinals) == 1, (
            f"The assembled roster for {name} numbers `{stem}` from {min(ordinals)} rather than "
            "1, so either the first member of the sequence was dropped or the seed numbers from "
            "somewhere else. This assertion is the one in this test that rests on a convention "
            "rather than on arithmetic — contiguity above holds whatever the sequence starts at."
        )


def test_every_user_the_platform_will_launch_appears_in_the_roster_of_its_context(
    mock_platform: Any,
) -> None:
    """The weaker half of "no member is dropped", kept because it fails differently.

    A membership container carries no total, so nothing in the roster can say
    whether the roster is short. What can say it is the launch page: every user
    it will sign a launch for in a context is demonstrably enrolled in that
    context, learned by driving the launch rather than by reading the roster.

    **A reviewer measured how weak this is, and the measurement is why the test
    above exists.** Both launch users sit at the head of every roster, so a page
    slice that loses one member per boundary satisfies this test completely. It
    is kept rather than deleted because it fails for a reason the numbering test
    cannot: a roster that is complete and *of the wrong people* keeps its
    sequence intact and loses these users.

    **What this does not reach**, said rather than implied: it is a lower bound.
    The launch page offers a handful of users and the roster is bigger than that,
    so a drop that lands on a member nobody launches as is invisible here.

    A dropped student is expected to be *present* with a non-Active status rather
    than absent: SPEC §3.4 has the tool learn about drops from NRPS enrollment
    data, which it cannot do from a member that is simply gone.
    """
    walked = walked_rosters(mock_platform)
    expected = {context.context_id: context.subjects for context, _ in walked}
    assert any(expected.values()), (
        "No launch carried a `sub`, so there is nothing to look for in the roster and this test "
        "would pass against any roster at all, including an empty one."
    )
    for context, pages in walked:
        present = {str(member.get(MEMBER_ID)) for member in members_across(pages)}
        missing = sorted(context.subjects - present)
        assert not missing, (
            f"The platform signs launches into context {context.context_id} for {missing}, and "
            f"the assembled roster for it — {len(present)} members over {len(pages)} pages — "
            "does not carry them. Either paging dropped a member, or the roster omits an "
            "enrollment the platform will still launch. SPEC §3.4 has the tool learn about drops "
            "from NRPS, so a dropped student belongs on the roster carrying a non-Active status "
            "rather than absent from it."
        )
