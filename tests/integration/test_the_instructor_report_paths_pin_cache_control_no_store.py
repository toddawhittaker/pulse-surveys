"""E4-15's deferred entry — `Cache-Control: no-store` on both instructor report routes.

`docs/tickets/e4/deferred.md` carries the entry this module closes: E4-07's two
routes set the header and nothing in this suite pins either one, so removing a
line survives. The two routes are the report for one section and one course week,
and the published-week list beside it.

**Why a module of its own rather than an addition to
`test_the_instructor_section_list_answers_the_shape_e4_18_declares.py`, said out
loud because the work order left it to the author.** That module's own docstring
scopes it to E4-18: "What the instructor section list answers, and how", against
that ticket's criteria 3, 4 and 6, over a world its own
`tests/fixtures/instructor_sections.py` builds for the section *list*. Its
`no-store` test is E4-18's criterion 6 — one route, one ticket, one criterion. The
two routes here are E4-07's, they are read through `report_door`'s world rather
than that one, and the obligation is E4-15's deferral rather than E4-18's
criterion. Extending that module would have made its docstring false about its own
subject (`docs/MISTAKES.md` entry 1) and would have put three tickets' pins in one
file. Three modules now hold this header, one per ticket that shipped a route:
E2-15's student pair, E4-18's list, and this pair.

**Why neither test carries the `invariant` mark, and it is not an oversight.**
`no-store` is caching hygiene on a response the requesting instructor is entitled
to — a browser or an intermediate cache holding a copy of her own section's report
after she signs out on a shared machine — not a line about one person seeing
another's data. SPEC §4.1's own denial modules are the right home for a
cross-scope leak, and E4-07's are already there, `invariant`-marked, in the
isolated pass. This is an ordinary pair, and E2-15's module states the same
distinction for the same reason.

**One test per route, deliberately, rather than one test reading both
responses.** Each route's header is a separate statement in the handler that an
implementer can drop independently, so "removing either route's header turns a
test red" is proven once per route rather than by a single assertion that would
pass with only one of the two lines in place.

**Which failure a red is.** Both tests drive the built application over HTTP
through `report_door`, whose whole world is E4-03's and E1's machinery; neither
imports a deliverable of this ticket. So a red is an assertion about a status or a
header, never an error in setup (`docs/MISTAKES.md` entries 44 and 47).

**Both are green-on-arrival controls, and that is why they are written.** The
routes set the header today. A test that only ever went red on new work would have
nothing to say about a line that is already there and pinned by nothing — which is
`docs/MISTAKES.md` entry 2 exactly: behaviour shipped with nothing asserting it. A
red in either one on a tree where nothing else changed is this module or the
fixture world, not the routes.
"""

import pytest
from fixtures.report_api import FULL_WEEK, ReportDoor

pytestmark = pytest.mark.integration

# Written out here rather than imported from `tests/fixtures/instructor_sections.py`,
# which spells the same two strings for E4-18's route. The header and its one
# acceptable value are the subject of these tests, and a subject imported from the
# module that also holds another ticket's copy of it is one rename away from two
# suites agreeing about a name neither asserts.
CACHE_CONTROL_HEADER = "Cache-Control"
NO_STORE = "no-store"


def test_the_report_route_answers_cache_control_no_store(report_door: ReportDoor) -> None:
    """The report for one section and one course week answers `Cache-Control: no-store`.

    The response carries this section's rating distributions, its rates, its
    per-stream summaries and — above SPEC §4's threshold — its students' raw
    comments. A cache that kept a copy after the instructor signed out on a shared
    machine goes on serving all of it, and a cache that kept a *stale* copy goes on
    showing a comment a moderation decision has since collapsed (§5.2).

    **The mutation this kills:** deleting the statement that sets
    `Cache-Control` on the report response — today green, the line removed, red.
    Nothing else in this suite notices its loss: E2-15's pair asserts the header of
    the two student routes and E4-18's asserts the section list's.

    **The near miss it must survive:** a header present and spelled some other way
    — `no-cache`, `private`, `max-age=0` — each of which still lets a cache or a
    browser retain the body under some conditions, where only `no-store` refuses to
    retain it at all. Compared as an exact value rather than as "some caching
    header is present", which is how E2-15's own pair compares it.

    The 200 is asserted first because a header read off a refusal is a header
    assertion about a refusal (`docs/MISTAKES.md` entry 3): this world's clock
    stands after every one of its six windows has closed, so the week asked for is
    published and the section is the one this session's launch granted her.
    """
    answered = report_door.report(course_week=FULL_WEEK)
    assert answered.status_code == 200, (
        f"The report for course week {FULL_WEEK} answered {answered.status_code} for the section "
        "this session teaches, so the header assertion below would be about a refusal rather than "
        f"about a report. Body begins {answered.text[:400]!r}."
    )
    header = answered.headers.get(CACHE_CONTROL_HEADER)
    assert header == NO_STORE, (
        f"The report route answered with `{CACHE_CONTROL_HEADER}: {header!r}` rather than "
        f"`{NO_STORE}`. The body carries this week's comments, summaries and rates, and E4-15's "
        "deferred entry is that nothing in this suite pinned the header the route already sets — "
        "this is that pin."
    )


def test_the_published_weeks_route_answers_cache_control_no_store(
    report_door: ReportDoor,
) -> None:
    """The published-week list answers `Cache-Control: no-store` too.

    It carries less than the report does and it is not nothing: which weeks of a
    section have closed windows, for a section the reader is only entitled to
    because of a grant that can be withdrawn. It is also the read the report page
    makes first, so a cached copy is what a signed-out browser would page a report
    from.

    **The mutation this kills:** the header set on the report and left off the list
    beside it — the asymmetry an implementer produces by writing one line and not
    the second, and the exact state E2-15's boundary review found between the
    student GET and the student POST.

    **The near miss it must survive:** the same as its sibling — a differently
    spelled caching header. Compared as an exact value.

    **Why this is not the same test twice.** The two routes are two handlers and
    two statements; a single test reading both responses would pass with either
    line present. The pair is what makes each one's absence a red of its own, and
    the ticket's own wording asks for both directions proven once.
    """
    answered = report_door.published_weeks()
    assert answered.status_code == 200, (
        f"`GET` on the published-week list answered {answered.status_code} for the section this "
        f"session teaches. Body begins {answered.text[:400]!r}."
    )
    header = answered.headers.get(CACHE_CONTROL_HEADER)
    assert header == NO_STORE, (
        f"The published-week list answered with `{CACHE_CONTROL_HEADER}: {header!r}` rather than "
        f"`{NO_STORE}`. It names which weeks of one section a person holding a teaching grant may "
        "read, and the report page asks it before it asks for a report."
    )


def test_the_two_routes_are_read_through_one_session_and_both_answer(
    report_door: ReportDoor,
) -> None:
    """The must-be-green control the pair above rests on: both routes answer this reader.

    Each test above asserts a header on a 200, and each guards its own status. What
    neither can say on its own is that the two reads are the *same* reader against
    the *same* section — which is what makes the pair a statement about two routes
    rather than about two worlds. A fixture that granted the teaching assignment for
    one read and not the other would let one test pass and the other fail on a
    status, and the failure would name a header
    (`docs/MISTAKES.md` entry 30: neither the green nor the red would mean
    anything).

    So both are read here in one test, in one world, and both are required to
    answer 200 — and the section they are read for is asserted to be the same one.

    **The mutation this kills:** a `report_door` whose two route helpers resolve
    different sections, or a world where the teaching grant is written for one
    section and the reads are made against another.
    """
    section = report_door.rows.taught_section_id
    report = report_door.report(course_week=FULL_WEEK, section_id=section)
    published = report_door.published_weeks(section_id=section)
    assert (report.status_code, published.status_code) == (200, 200), (
        f"The report answered {report.status_code} and the published-week list "
        f"{published.status_code} for one section, read with one session. Both routes stand behind "
        "the same teaching-instructor grant, so a pair of statuses that disagree is a scope "
        "question rather than a caching one, and the two header tests beside this would report it "
        f"as a missing header.\n\nReport body begins {report.text[:300]!r}; list body begins "
        f"{published.text[:300]!r}."
    )
