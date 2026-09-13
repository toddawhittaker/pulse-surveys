"""Who may read a Monday report, and what a refusal says — ticket E4-07, criteria 1 and 2.

E4-07's authorization is deliberately narrow: **the requesting session's own
taught sections, nothing else.** The `teaching_instructor` view is the source, and
the chokepoint rule — a request resolves only its own authenticated subject's
scope — is already the carried law. So a section id outside the session's own
teaching set is a refusal driven from the session rather than a parameter check,
and criterion 1 requires it to be indistinguishable from a section that does not
exist:

> a section she does not teach — including one that does not exist — refuses with
> the same status and body, asserted as a pair.

Criterion 2 is the other half, one layer up: a student session and a leadership
session are refused these routes outright, per role, because leadership's read of
this report is E9's drill-down and not this route.

**The two refusals are different refusals, and the statuses are what tell them
apart.** Work-order decision 3 settles 404 with one shared body for an
out-of-scope or absent section; decision 2 settles that a wrong-role session is
refused "exactly as a wrong-role session is refused student routes", which is
`tests/fixtures/student_read.py`'s 401 with `WWW-Authenticate: Bearer`. That
difference is load-bearing here rather than incidental: a leadership session
answered 404 would have *passed the role gate* and been refused for scope, which
is E9's shape arriving three epics early. So each role test asserts the 401 and
says the 404 is the near miss.

**Every probe carries a positive control** (`docs/MISTAKES.md` entry 35). A guard
that only ever reports absence cannot tell you which mechanisms it can see, and a
refusal proves nothing about scoping if the route refuses everybody:

  - the teaching instructor's **own** section answers 200 with a report, in this
    module, before any refusal is read;
  - the student session's control is `GET /student/survey`, which that role
    certainly reads — a 200 there and a 401 here is a statement about the role
    gate rather than about a broken session;
  - the leadership session's control is the landing that issued it. `ReportDoor`
    is built through `session_token_at`, which refuses a launch that did not land
    on `/app/leadership`, so a session that reaches these tests is a leadership
    session and not a no-access page. **The disclosed limit** (`docs/MISTAKES.md`
    entry 14): E4 ships no leadership read route, so there is no relation of this
    API a dean certainly reads, and the control is the door rather than a second
    read. E9 is where that control becomes available.

**Marked `invariant` at the module level**, which puts it in the isolated §4.1
pass and satisfies
`tests/unit/test_every_confidentiality_denial_module_sits_inside_the_invariant_pass.py`.

**Which failure a red is, before E4-07 lands.** Every test reaches the routes
through `report_api_contract`, whose lookups are `pytest.fail` calls naming the
deliverable — the router, the dependency — so the first red is a FAILED naming
what is missing rather than an error in setup (`docs/MISTAKES.md` entry 44).
"""

from typing import Any
from uuid import UUID

import pytest
from fixtures.report_api import FULL_WEEK, ReportDoor
from fixtures.routing import dependencies_of
from fixtures.student_read import STUDENT_READ_PATH

pytestmark = [pytest.mark.integration, pytest.mark.invariant]

# Both of E4-07's routes, each with the arguments it is asked with. **The
# arguments travel with the name**, because the two signatures differ — the
# report names a course week and the published-week list names none — and a
# parametrization carrying only the names calls one of them wrongly. Written this
# way after the first version did exactly that: `getattr(door, route)()` raised
# `TypeError` on the report half for every role, which is a red that says nothing
# about a role gate and would have gone on saying nothing after the routes were
# built. A role test has to drive *both* routes or criterion 2 is asserted over
# whichever one happens to take no arguments.
BOTH_ROUTES = (
    ("report", {"course_week": FULL_WEEK}),
    ("published_weeks", {}),
)
ROUTE_IDS = [name for name, _arguments in BOTH_ROUTES]


def spellings_of(value: Any) -> set[str]:
    """One identifier in every spelling a JSON body could carry it in.

    A uuid hyphenated and hyphen-stripped: `str(...)` is what anything rendering
    one produces by default, and `uuid.hex` is the near miss that walks through a
    search for the first — the pair
    `tests/integration/test_the_dev_console_names_nobody.py` had to add after a
    mutation battery walked past it.
    """
    written = str(value)
    found = {written}
    if isinstance(value, UUID):
        found.add(value.hex)
    return found


def surface_of(answered: Any) -> str:
    """Everything a client reading this response could see: its headers and its body.

    The headers as well as the body, because an identifier can ride one — a
    `Location`, an `ETag` built out of the row it describes — and a scan blind to
    them reports a clean answer.
    """
    headers = " ".join(f"{name}: {value}" for name, value in answered.headers.items())
    return f"{headers} {answered.text}"


def test_the_teaching_instructors_own_section_answers_her_report(
    report_door: ReportDoor,
) -> None:
    """The positive control every refusal below rests on — criterion 1's first half.

    `docs/MISTAKES.md` entry 35: a guard that only ever reports absence cannot
    tell you which mechanisms it can see. If the report route refused every
    section — a `teaching_instructor` join that matches nothing, a dependency that
    never resolves a subject — every assertion in this module would still pass and
    would be a statement about a route that answers nobody.

    **The mutation this kills:** the scope query widened to nothing, or narrowed
    to nothing. Its near miss is the test below it: a route that answered 200 for
    *any* section would pass here and fail there, which is why the pair is the
    unit rather than either half.
    """
    answered = report_door.report(course_week=FULL_WEEK)
    assert answered.status_code == 200, (
        f"The report for the section this session teaches answered {answered.status_code}. The "
        "launching person holds an `INSTRUCTOR` assignment scoped to that section — the row "
        "`record_teaching_instructor` writes and the `teaching_instructor` view answers over — so "
        f"this is the one section E4-07 says she may read. Body begins {answered.text[:400]!r}."
    )
    body = answered.json()
    assert isinstance(body, dict) and body, (
        f"The report answered 200 with {answered.text[:200]!r}, which carries no members. An empty "
        "body satisfies every 'the payload does not contain X' assertion in this epic."
    )


def test_a_section_she_does_not_teach_refuses_exactly_as_one_that_does_not_exist(
    report_door: ReportDoor, report_api_contract: Any
) -> None:
    """Criterion 1's pair, asserted as a pair: same status, same body, same shape.

    Work-order decision 3 settles the answer and the reason: scope is one query
    against the `teaching_instructor` view, "so absence and out-of-scope take the
    same code path — no existence oracle by shape, body, or code path". A reader
    who can tell the two apart can enumerate which sections exist by asking about
    them, which is a fact about the institution nobody outside it is owed.

    **The mutation this kills:** a 403 for out-of-scope beside a 404 for absent —
    the shape an implementation reaches for when it validates the parameter first
    and consults the session second. Its near miss is a *shared* status with two
    different bodies ("not found" against "not yours"), which is why the body is
    compared as text rather than only as a status.
    """
    outside = report_door.report(
        course_week=FULL_WEEK, section_id=report_door.rows.untaught_section_id
    )
    absent = report_door.report(
        course_week=FULL_WEEK, section_id=report_api_contract.a_section_that_does_not_exist()
    )

    assert outside.status_code == report_api_contract.out_of_scope_status, (
        f"A section this instructor does not teach answered {outside.status_code} rather than "
        f"{report_api_contract.out_of_scope_status}. E4-07's work order settles the refusal pair as "
        "404 for both halves, matching the no-oracle rule the dev routes already follow. Body "
        f"begins {outside.text[:400]!r}."
    )
    assert absent.status_code == outside.status_code, (
        f"A section that does not exist answered {absent.status_code} and one outside the teaching "
        f"set answered {outside.status_code}. Two statuses is an existence oracle: ask about a "
        "section id and the difference tells you whether it is a real section."
    )
    assert absent.text == outside.text, (
        "The two refusals carry different bodies.\n"
        f"  outside the teaching set: {outside.text[:300]!r}\n"
        f"  no such section:          {absent.text[:300]!r}\n\n"
        "Criterion 1 asks for the same status *and* the same body; a shared 404 whose detail says "
        "'not found' in one case and 'not yours' in the other is the same oracle one layer in."
    )


def test_neither_refusal_names_the_section_it_was_handed(
    report_door: ReportDoor, report_api_contract: Any
) -> None:
    """The refusal repeats nothing it was given, in either spelling of a uuid.

    A body that echoes the section id back is not an oracle by itself — the caller
    supplied it — but it is the currency every later leak travels in, and E4-07's
    known traps name the pair: "the refusal pair must be indistinguishable in
    body, not merely in status". A refusal that echoes cannot be identical to one
    about a different id.

    **The mutation this kills:** a detail message interpolating the section id,
    which makes the two refusals differ by construction while both remain 404.
    """
    untaught = report_door.rows.untaught_section_id
    absent = report_api_contract.a_section_that_does_not_exist()

    handed = (
        (untaught, "a section outside the teaching set"),
        (absent, "a section that does not exist"),
    )
    for section_id, what in handed:
        answered = report_door.report(course_week=FULL_WEEK, section_id=section_id)
        surface = surface_of(answered)
        echoed = sorted(value for value in spellings_of(section_id) if value in surface)
        assert not echoed, (
            f"The refusal for {what} repeats {echoed} back to the caller. Surface begins "
            f"{surface[:300]!r}."
        )


def test_the_published_week_list_refuses_the_same_pair_the_same_way(
    report_door: ReportDoor, report_api_contract: Any
) -> None:
    """Criterion 1 over the second route — both routes are behind the same scope.

    E4-07's scope is a property of the session and the section, not of one
    endpoint, and the published-week list names a section too. A route that
    listed the weeks of any section anybody asked about would leak the shape of a
    term's calendar for a section the reader has no relationship with, and would
    do it from the endpoint nobody thinks of as the report.

    **The mutation this kills:** the scope check applied in the report handler
    rather than in the dependency both handlers share.
    """
    mine = report_door.published_weeks()
    assert mine.status_code == 200, (
        f"The published-week list for her own section answered {mine.status_code}; every assertion "
        f"below would then be about a route that refuses everybody. Body begins {mine.text[:400]!r}."
    )

    outside = report_door.published_weeks(section_id=report_door.rows.untaught_section_id)
    absent = report_door.published_weeks(
        section_id=report_api_contract.a_section_that_does_not_exist()
    )
    assert outside.status_code == report_api_contract.out_of_scope_status, (
        f"The published-week list for a section she does not teach answered {outside.status_code} "
        f"rather than {report_api_contract.out_of_scope_status}. Body begins {outside.text[:400]!r}."
    )
    assert (absent.status_code, absent.text) == (outside.status_code, outside.text), (
        f"The list route's two refusals differ: {absent.status_code} {absent.text[:200]!r} against "
        f"{outside.status_code} {outside.text[:200]!r}."
    )


@pytest.mark.parametrize(("route", "arguments"), BOTH_ROUTES, ids=ROUTE_IDS)
def test_a_student_session_is_refused_both_routes_by_role(
    report_door_as: Any, report_api_contract: Any, route: str, arguments: dict[str, Any]
) -> None:
    """Criterion 2, the student half, with the control that the session reads what it may.

    The refusal has to be the **role** gate rather than the scope gate, and the
    status is what says which: `require_instructor` refuses a session whose role
    is not the instructor one with the 401 `require_student` uses for the mirror
    case, while an out-of-scope section is a 404. A 404 here would mean this
    student session reached the scope query — the report's authorization resolved
    for somebody who holds no assignment at all.

    **The mutation this kills:** a route that takes its role from a parameter, or
    from the section's own teaching row, rather than from the session claims.
    **The control:** the same session, with the same jar emptied, reading
    `/student/survey` and getting 200 (`docs/MISTAKES.md` entry 35).
    """
    door = report_door_as("STUDENT")

    with door.carrying_no_cookie():
        allowed = door.tool.get(STUDENT_READ_PATH, headers=door.credential())
    assert allowed.status_code == 200, (
        f"This student session was answered {allowed.status_code} by `{STUDENT_READ_PATH}`, which "
        "is the route its role certainly reads. Until that is 200, a refusal from the instructor "
        "routes says nothing about roles — it says the session is not a session "
        f"(`docs/MISTAKES.md` entry 35). Body begins {allowed.text[:300]!r}."
    )

    with door.carrying_no_cookie():
        answered = getattr(door, route)(**arguments)
    assert answered.status_code == report_api_contract.role_refused_status, (
        f"A student session reading the instructor {route} route was answered "
        f"{answered.status_code}, not {report_api_contract.role_refused_status}. E4-07's work order "
        "settles that a wrong-role session is refused these routes exactly as it is refused a "
        f"student route. A {report_api_contract.out_of_scope_status} would be worse than a 200 "
        "would be obvious: it means the role gate let this session through and the scope query "
        f"answered it. Body begins {answered.text[:400]!r}."
    )


@pytest.mark.parametrize(("route", "arguments"), BOTH_ROUTES, ids=ROUTE_IDS)
def test_a_leadership_session_is_refused_both_routes_by_role(
    report_door_as: Any, report_api_contract: Any, route: str, arguments: dict[str, Any]
) -> None:
    """Criterion 2, the leadership half — this route is not E9's drill-down.

    SPEC §5.5 gives leadership a read-only render of this same report inside its
    own shell, and E4's breakdown puts every leadership and purview read in E9.
    Until then a dean holding no instructor assignment is not an instructor, and
    the route says so at the role gate. The `invariant` marker is here because the
    alternative — a leadership session admitted "since they would see it in E9
    anyway" — is a widening of who reads a section's raw comments, decided by a
    route rather than by the purview computation E9 builds.

    **The mutation this kills:** `require_instructor` written as "any session that
    is not a student", which admits every leadership role and Care besides.
    **The control:** this session exists and is a leadership one — the door is
    built through `session_token_at`, which refuses a launch that landed anywhere
    but `/app/leadership`. See this module's docstring for why that is the control
    available in E4 and what E9 makes possible instead.
    """
    door = report_door_as("DEAN")
    assert door.token, "The leadership launch issued an empty session; there is nothing to refuse."

    with door.carrying_no_cookie():
        answered = getattr(door, route)(**arguments)
    assert answered.status_code == report_api_contract.role_refused_status, (
        f"A leadership session reading the instructor {route} route was answered "
        f"{answered.status_code}, not {report_api_contract.role_refused_status}. Leadership's read "
        "of this report is E9's drill-down; nothing in E4 anticipates that shell. Body begins "
        f"{answered.text[:400]!r}."
    )


def test_both_routes_carry_the_instructor_session_dependency(
    report_door: ReportDoor, report_api_contract: Any
) -> None:
    """The gate is on both routes, read off the built application's dependency graph.

    The behavioural tests above are the ones that matter — `docs/MISTAKES.md`
    entry 47 is the incident where a route's gate was visible in the route table
    and discarded at dispatch — and this is the structural half beside them, for
    the failure they cannot see: a *third* route added later to the same module
    with no dependency on it. The match is on the dependency **object**, never on
    its name, so a route whose graph happens to contain something else called
    `require_instructor` is not a route that carries this project's check.
    """
    dependency = report_api_contract.require_instructor()
    routes = report_api_contract.route_objects(report_door.application)
    without = [
        getattr(route, "path", "?")
        for route in routes
        if dependency not in dependencies_of(getattr(route, "dependant", None))
    ]
    assert not without, (
        f"These `{report_api_contract.api_module}` routes do not carry "
        f"`{report_api_contract.require_instructor_name}` anywhere in their dependency graph: "
        f"{without}. E4-07's work order puts both routes behind it, and a route that resolves its "
        "own subject some other way is a second answer to 'whose sections are these'."
    )
