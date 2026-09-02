"""SPEC §4.1 item 1, asserted at last — ticket E2-09.

Item 1 reads: "Students never see comparables, benchmarks, university averages,
or **other sections** — in charts, text, tooltips, exports, or aria labels", and
it has carried the note *"Asserted from **E2**, the first epic with a
student-visible path and the scoping that gives 'another section' its meaning"*
since E0. This module is that assertion. Until E2-09 there was no student-visible
read path at all, so there was nowhere for the rule to bite; there is one now,
and this is the module the epic is named for.

**The inventory has a source the code cannot quietly shrink.** What "every
student-visible path" means is not a list somebody maintains — `docs/MISTAKES.md`
entry 2 is behaviour shipping with nothing asserting it, and a hand-kept
inventory is how a new route joins a system with nothing swept over it. It is
derived from the running application's own route table: every route whose
dependency graph contains `app.api.deps.require_student` is a route a student
session can reach, and the dependency is the same object the router registers, so
a route that omits it is not student-visible and a route that has it is in this
sweep the day it lands. The walk goes through
`tests/fixtures/routing.py::every_route` because FastAPI 0.141.1's
`include_router` appends an `_IncludedRouter` carrying no `path` at all, and the
obvious walk over `application.routes` sees four documentation paths and nothing
this project serves (dispute E2-04-01 has the printed list).

**Two controls, because a sweep for absence is satisfied by emptiness**
(`docs/MISTAKES.md` entries 3 and 35). A guard that enumerates a mechanism has to
be shown *finding* it on a subject that certainly has it, so a planted student
route on an application built here must appear in the inventory — and a planted
route beside it, identical but for the dependency, must not. And the inventory
over the real application must be non-empty, or "none of them names another
section" is a statement about no routes at all.

**The two-section pair is what gives "another section" its meaning.** The same
student is enrolled in section A and not in section B; the two are siblings of one
course in one term, and **both have a window open at the instant these reads are
taken**, so a read path that has lost its enrollment predicate has something to
return. Everything B-shaped must be absent from every answer — from the body, and
from the *shape of a refusal* too: a request naming section B that is answered
differently from a request naming a section that does not exist has confirmed B
exists, which is the disclosure whether or not the data follows (ADR 0074/0079,
and `backend/app/api/dev.py`'s own 404-with-no-distinction pattern).

**The mutation this module exists to kill** is the loosened enrollment predicate:
the read assembly's query over `enrollment` with its `user_id` filter dropped, or
widened to the course, or to the term. Each of those returns section B to a
student who is not in it, and each is a plausible thing to write. The near miss
each test must survive is a read that returned *nothing* — a refusal, an empty
list, a 500 — which names no other section either; so every test below first
requires the answer to name the section the student **is** in.

**Two denials here are not item 1's**, and they are here rather than next door
because they are §4 denials about the same one read path and a module half inside
the isolated pass is what
`tests/unit/test_every_confidentiality_denial_module_sits_inside_the_invariant_pass.py`
exists to stop. A classmate's stored comment is other individuals' raw data,
which SPEC §5.4 forbids a student view by name; and a session that is not this
student's must be refused rather than answered, which is the access half of the
same rule.

**The marker sits at module level**, in the list form beside `integration` and
`lti`, and not on each test: the rule that sweep pins is *where* the mark sits, so
that this module's next denial test inherits it.
"""

from typing import Any
from uuid import uuid4

import pytest
from fixtures.routing import every_route
from fixtures.student_read import (
    AUTHENTICATE_HEADER,
    AUTHENTICATE_SCHEME,
    REFUSED_STATUS,
    STUDENT_READ_PATH,
    StudentReadDoor,
    around,
    response_surface,
)

pytestmark = [pytest.mark.invariant, pytest.mark.integration, pytest.mark.lti]

# The two paths the planted control registers. Named so that no implementation
# could arrive at either by accident, and neither is a path this project serves.
PLANTED_STUDENT_PATH = "/e2-09-planted/student-visible"
PLANTED_OPEN_PATH = "/e2-09-planted/open-to-anybody"

# The query parameter names a caller could try to reach another section by. None
# of them is part of the route's interface — E2-09 settles that `GET
# /student/survey` takes no parameters at all — which is exactly why they are
# tried: a parameter nobody documented is how a read path grows a way to ask for
# somebody else's section.
#
# **Three names are an inventory of a convention, not a closed class**
# (`docs/MISTAKES.md` entry 14). A parameter spelled some fourth way is not
# reached here, and no amount of widening closes the set. What closes it is the
# sweep above: a route in the inventory that takes a *path* parameter fails
# outright, and the body scan runs over whatever the route answers however it was
# asked. This is the cheap check that the ordinary spellings do nothing.
SECTION_PARAMETERS = ("section_id", "section", "section_code")


def dependencies_of(dependant: Any, seen: set[int] | None = None) -> list[Any]:
    """Every callable in one route's dependency graph, at any depth.

    FastAPI holds a route's dependencies as a tree of `Dependant` objects, each
    carrying the callable it resolves in `.call` and its own sub-dependencies in
    `.dependencies`. A walk one level deep would see a dependency declared on the
    route and miss one declared on a dependency of it — and "reachable by a
    student session" is a property of the whole graph, not of its first layer.
    """
    seen = set() if seen is None else seen
    if id(dependant) in seen:
        return []
    seen.add(id(dependant))
    found: list[Any] = []
    call = getattr(dependant, "call", None)
    if call is not None:
        found.append(call)
    for child in getattr(dependant, "dependencies", ()) or ():
        found.extend(dependencies_of(child, seen))
    return found


def student_visible_routes(application: Any, dependency: Any) -> list[Any]:
    """Every route on `application` a student session can reach.

    The inventory SPEC §4.1 item 1 is swept over, and the whole of why it is
    derived rather than listed: its source is the application object, which is
    the thing that decides what is served. A route added without this dependency
    is not student-visible and is not swept; a route added with it is swept the
    day it is registered, with nothing to remember to update.
    """
    return [
        route
        for route in every_route(application)
        if getattr(route, "dependant", None) is not None
        and dependency in dependencies_of(route.dependant)
    ]


def paths_of(routes: list[Any]) -> set[str]:
    """The paths of a set of routes, for a message a reader can act on."""
    return {path for path in (getattr(route, "path", None) for route in routes) if path}


# ---------------------------------------------------------------------------
# The controls on the instrument, run before the tree is judged with it.
# ---------------------------------------------------------------------------


def test_the_student_route_inventory_finds_a_planted_route_and_spares_its_near_miss(
    require_student_dependency: Any,
) -> None:
    """The instrument, both directions, on an application built here.

    `docs/MISTAKES.md` entry 35: a guard that enumerates a mechanism must be
    required to *find* it on a subject that certainly has it, because a guard that
    only ever reports absence cannot tell you what it can see. So two routes are
    planted on an application of this test's own making — one carrying
    `require_student`, one identical but for that — and the inventory must return
    exactly the first.

    **Registered through `include_router`, which is the half that matters.** On
    the pinned FastAPI a router's routes are not copied onto the application: an
    `_IncludedRouter` is appended, carrying no `path` and no `dependant`, and a
    sweep walking `application.routes` directly finds nothing of it. That is
    measured, not read (dispute E2-04-01), and it is why this control plants its
    routes the way the real application registers its own rather than decorating
    the application object.

    **The mutations this kills.** A walk over `application.routes` without
    `every_route`'s recursion, which reports the real application as serving no
    student route at all and makes the sweep below silent. And a match on the
    dependency's *name* rather than on the object, which would enrol any route
    whose graph happens to contain something else called `require_student`.

    **The near miss it must spare** is the second planted route: a sweep that
    returned every route would report the whole application as student-visible
    and would be red against correct code everywhere it was pointed.
    """
    from fastapi import APIRouter, Depends, FastAPI

    router = APIRouter()

    @router.get(PLANTED_STUDENT_PATH)
    def planted_student_route(_: Any = Depends(require_student_dependency)) -> dict[str, str]:
        return {}  # pragma: no cover - never called; only its dependency graph is read

    @router.get(PLANTED_OPEN_PATH)
    def planted_open_route() -> dict[str, str]:
        return {}  # pragma: no cover - never called; only its dependency graph is read

    application = FastAPI()
    application.include_router(router)

    found = paths_of(student_visible_routes(application, require_student_dependency))

    assert PLANTED_STUDENT_PATH in found, (
        f"The inventory did not find `{PLANTED_STUDENT_PATH}`, a route registered through "
        "`include_router` whose only dependency is `require_student`. It found "
        f"{sorted(found)}.\n\n"
        "A sweep that cannot see the mechanism reports a clean application however many student "
        "routes it serves, and the §4.1 item 1 assertion below would be silence dressed as a pass. "
        "The likeliest cause is walking `application.routes` rather than "
        "`tests/fixtures/routing.py::every_route`: FastAPI 0.141.1 appends an `_IncludedRouter` "
        "that carries neither `path` nor `dependant`, so the routes are one recursion away."
    )
    assert PLANTED_OPEN_PATH not in found, (
        f"The inventory also claimed `{PLANTED_OPEN_PATH}`, which carries no student-session "
        "dependency at all. A sweep that enrols every route is red against every correct "
        "application, and it would be deleted rather than fixed."
    )


def test_the_running_application_serves_at_least_one_student_visible_route(
    student_read_door: StudentReadDoor, require_student_dependency: Any
) -> None:
    """The inventory over the real application is not empty.

    Every assertion in this module is of the form "no student-visible route names
    another section". Over an empty inventory that is true of an application
    serving the whole institution's rosters, which is `docs/MISTAKES.md` entry 3
    in its plainest form — so the non-emptiness is asserted first and separately,
    with its own message.

    **The mutation it kills:** the route registered on a router nobody includes,
    or a `require_student` that the route declares in some way the walk cannot
    see. Either ships a student read path outside every sweep in this file.
    """
    routes = student_visible_routes(student_read_door.application, require_student_dependency)

    assert routes, (
        "The running application serves no route whose dependency graph contains "
        "`require_student`, so the §4.1 item 1 sweep below judged nothing and its silence means "
        f"nothing. E2-09 adds `GET {STUDENT_READ_PATH}` behind that dependency and registers its "
        "router in `app.main`; the paths the application does serve are "
        f"{sorted(paths_of(every_route(student_read_door.application)))}."
    )
    assert STUDENT_READ_PATH in paths_of(routes), (
        f"`{STUDENT_READ_PATH}` is not among the student-visible routes ({sorted(paths_of(routes))})"
        ". That path is E2-09's settled interface — no path parameters, no query parameters, one "
        "round trip — and E2-10's form is written against it."
    )


# ---------------------------------------------------------------------------
# SPEC §4.1 item 1.
# ---------------------------------------------------------------------------


def test_no_student_visible_route_names_a_section_the_student_is_not_enrolled_in(
    student_read_door: StudentReadDoor, require_student_dependency: Any
) -> None:
    """SPEC §4.1 item 1: a student-visible path never names another section.

    The student is enrolled in one section and not in its sibling. Both are
    sections of the same course in the same term, both carry a window that is open
    at the instant this reads, and both have a question set to serve — so the
    other section is not absent from the answer because there was nothing to say
    about it. It is absent because the read path is scoped to this student's own
    enrollment.

    **The mutation this kills — the headline one for this ticket.** The read
    assembly's enrollment predicate, loosened: the `user_id` filter dropped, or
    the query widened from the student's enrollment to the section's course or to
    the term. Every one of those returns section B here, and every one of them is
    an ordinary thing to write. **The near misses it must survive**: an answer
    that names the enrolled section and nothing else (asserted green below), and a
    scan looking for strings the two sections *share* — the term, the course, the
    week their windows are over — which would report a correct answer as a leak,
    which is why the needle set is B's values minus A's.

    **What makes a green mean something, in order.** The answer has to be a 200
    naming the student's own section, so a refusal cannot pass this by carrying
    nothing. And the needle set has to contain the other section's identifier and
    its §2.2 code, so the scan is looking for the things that identify a section
    rather than for whatever happened to be on the row. There is deliberately no
    planted-string canary beside those two: the scan is a plain substring test
    over a surface that has already been required non-empty and required to
    contain a value of the same kind, so a plant would be an assertion that cannot
    fail rather than a guard — the canary belongs where a *pattern* could go blind
    (`docs/MISTAKES.md` entry 3), and there is no pattern here.

    **This sweep is over the routes it can drive, and that is a disclosed limit.**
    Every student-visible route that answers GET and takes no path parameter is
    read and scanned. A GET route that takes one **fails this test** rather than
    being skipped — a route the sweep cannot drive is a route the sweep does not
    cover, and the repair is to give it a driver here in the same change. A route
    that answers only some other method (E2-08's `POST` submit, once both merge)
    is outside this sweep's reach and is not silently counted: it is named in the
    failure message's inventory and owned by the module that drives it.
    """
    routes = student_visible_routes(student_read_door.application, require_student_dependency)
    assert routes, (
        "The running application serves no student-visible route, so this sweep read nothing. "
        "`test_the_running_application_serves_at_least_one_student_visible_route` is where that is "
        "diagnosed."
    )

    undriveable = sorted(
        getattr(route, "path", "")
        for route in routes
        if "{" in getattr(route, "path", "") and "GET" in (getattr(route, "methods", None) or set())
    )
    assert not undriveable, (
        f"These student-visible routes answer GET and take a path parameter: {undriveable}. This "
        "sweep drives a parameterless GET, so it cannot read them — and a route it cannot read is "
        "a route SPEC §4.1 item 1 is unasserted over. Give it a driver here, in the same change "
        "that adds it; a sweep that skipped it would report a clean pass over a path nobody had "
        "looked at (`docs/MISTAKES.md` entry 2)."
    )

    world = student_read_door.world
    forbidden = world.anything_shaped_like_the_other_section()
    assert str(world.other_section_id) in forbidden, (
        f"The other section's identifier ({world.other_section_id}) is not among the values this "
        f"test searches for ({sorted(forbidden)}). It is the one string that names that section in "
        "every answer a join could produce, so a search without it is looking for the wrong thing."
    )
    assert world.other_section_code in forbidden, (
        f"The other section's §2.2 code ({world.other_section_code!r}) is not among the values this "
        f"test searches for ({sorted(forbidden)}). A code is how a section names itself to a "
        "person, and it is what an answer would carry if it rendered one."
    )

    scanned: list[str] = []
    for route in routes:
        path = getattr(route, "path", "")
        if "GET" not in (getattr(route, "methods", None) or set()):
            continue
        answered = student_read_door.get(path)
        assert answered.status_code == 200, (
            f"`GET {path}` answered {answered.status_code} for a student with a live enrollment "
            f"and an open window. Body begins {answered.text[:300]!r}. A refusal names no other "
            "section either, so this sweep cannot be allowed to pass over one."
        )
        surface = response_surface(answered)
        assert str(world.enrolled_section_id) in surface, (
            f"`GET {path}` answered 200 without naming the section this student **is** enrolled in "
            f"({world.enrolled_section_id}). Body begins {answered.text[:300]!r}. E2-09's answer "
            "carries the section per live enrollment, and an answer that names neither section "
            "would pass every assertion below while telling the student nothing."
        )
        leaked = sorted(value for value in forbidden if value in surface)
        assert not leaked, (
            f"`GET {path}` named {len(leaked)} value(s) belonging to a section this student is not "
            f"enrolled in: {leaked[:5]}. The first sits in {around(surface, leaked[0])!r}.\n\n"
            "SPEC §4.1 item 1: students never see other sections, in any surface. The two sections "
            "here are siblings of one course in one term and both have an open window, so an "
            "answer carrying the other one is a query that joined on the course, on the term, or "
            "on the week — or an enrollment predicate that lost its `user_id` filter — rather than "
            "on this student's own enrollment.\n\n"
            "Everything the two sections share is excluded from the search, so what is reported "
            "here belongs to the other section alone."
        )
        scanned.append(path)

    assert scanned, (
        f"None of the student-visible routes {sorted(paths_of(routes))} answers GET, so this sweep "
        "scanned nothing at all. Item 1 is about what a student is *shown*; a read path that "
        "cannot be read is not one."
    )


@pytest.mark.parametrize("parameter", SECTION_PARAMETERS)
def test_naming_another_section_is_answered_exactly_as_naming_one_that_does_not_exist(
    student_read_door: StudentReadDoor, parameter: str
) -> None:
    """A refusal is indistinguishable from a nonexistence (ADR 0074/0079).

    E2-09's route takes no parameters, so nothing here is asking it to honour one:
    what is asserted is that adding one changes nothing observable. Three reads —
    plain, one naming the section this student is not in, one naming a section
    that does not exist anywhere — and the last two must be answered identically.
    A `404` for the invented identifier beside a `403` for the real one is a leak
    on its own: it confirms that section B exists, which is a fact about the
    institution's sections that a student may not learn from this path.

    **The mutation this kills:** a read path that grows a section parameter, and
    then tells "you may not see this section" apart from "there is no such
    section" — the shape `backend/app/api/dev.py` already refuses one door over,
    and the reason ADR 0079 pins one answer for both.

    **The near miss it must survive**: a route that legitimately ignores unknown
    query parameters answers all three reads the same way, which is the pass.

    **The body comparison calibrates itself**, and that is deliberate rather than
    a hedge. Two plain reads are taken first: if the answer is byte-identical
    across them, the bodies of the two parametrised reads are required to equal it
    too, which is the strongest form of "indistinguishable". If it is not — an
    answer that echoes an instant would not be, and the development clock is
    moving while it is read — the status and the scan still hold unconditionally,
    and the message says which half was measured. Demanding equality of a body
    that is not stable would be a red nobody could fix.
    """
    world = student_read_door.world
    forbidden = world.anything_shaped_like_the_other_section()

    first = student_read_door.get()
    second = student_read_door.get()
    named = student_read_door.get(**{parameter: str(world.other_section_id)})
    invented = student_read_door.get(**{parameter: str(uuid4())})

    assert first.status_code == 200, (
        f"The plain read answered {first.status_code}, so there is no ordinary answer for the two "
        f"parametrised reads to be compared against. Body begins {first.text[:300]!r}."
    )
    assert named.status_code == invented.status_code, (
        f"`?{parameter}=` naming the section this student is not enrolled in was answered "
        f"{named.status_code}, and naming a section that does not exist at all was answered "
        f"{invented.status_code}. Two different answers tell the caller which of the two "
        "identifiers is real — a refusal that is distinguishable from a nonexistence discloses "
        "exactly what SPEC §4.1 item 1 keeps from a student, whether or not any data follows "
        "(ADR 0074/0079)."
    )
    assert named.status_code == first.status_code, (
        f"`?{parameter}=` changed the answer's status from {first.status_code} to "
        f"{named.status_code}. E2-09's route takes no parameters, so a parameter that changes the "
        "answer is a way to ask this path about a section, and the first thing anybody would ask "
        "it about is a section they are not in."
    )

    if first.text == second.text:
        assert named.text == invented.text == first.text, (
            f"Two plain reads of `{STUDENT_READ_PATH}` are byte-identical, so this answer is "
            f"stable — but adding `?{parameter}=` changed it. Naming the other section answered "
            f"{named.text[:200]!r} and naming a section that does not exist answered "
            f"{invented.text[:200]!r}. A route with no parameters answers the same thing whatever "
            "it is asked with; a body that varies is a parameter being honoured, and this one "
            "names a section."
        )

    for answered, what in ((named, "the other section"), (invented, "a section nobody has")):
        surface = response_surface(answered)
        leaked = sorted(value for value in forbidden if value in surface)
        assert not leaked, (
            f"Asking `?{parameter}=` for {what} was answered with {leaked[:5]}, which names the "
            f"section this student is not enrolled in. First occurrence: "
            f"{around(surface, leaked[0])!r}."
        )


def test_a_classmates_submission_is_never_in_this_students_answer(
    student_read_door: StudentReadDoor,
) -> None:
    """SPEC §5.4 and §4: a student sees their own answers and no other individual's.

    A classmate of this student has submitted in the same section, in the same
    week, in the window that is open right now. The student has submitted nothing.
    So the read path has a submission it could return for this section and week,
    and returning it would be the whole of the defect: SPEC §5.4 says a student
    is shown "their own section only … never other individuals' raw identifiable
    data", and §4 keys every response to its author.

    **The mutation this kills:** the own-submission lookup written over
    `(section, week)` and not over `(student, section, week)` — the same three
    columns E2-05 made `response` unique on, with the student left out. It is the
    natural mistake, it reads correctly, and in a section of one it is invisible;
    here the classmate's answer is the only one there is, so it is what comes
    back.

    **This is also the "no submission of my own" half of E2-09's boundary pair.**
    The student has not submitted, so what the answer must carry is *nothing* in
    that place — and asserting that against a database where the only stored
    answer belongs to somebody else is what makes the absence mean something
    rather than being true of an empty table.

    **The canary**: the classmate's comment and workload are read back out of the
    `answer` table before the scan, so a green says the values are stored and were
    not returned — not that nothing was stored (`docs/MISTAKES.md` entry 3).
    """
    world = student_read_door.world
    forbidden = world.anything_shaped_like_a_classmates_answer()

    missing = world.not_stored(forbidden)
    assert not missing, (
        f"The classmate's {missing} are not in the `answer` table, so this test is searching a "
        f"response for values nothing stored. What is stored: "
        f"{sorted(world.stored_answer_values())[:8]}. Until they are there, a clean scan means the "
        "fixture did not seed a submission rather than that the read path withheld one."
    )

    answered = student_read_door.get()
    assert answered.status_code == 200, (
        f"`GET {STUDENT_READ_PATH}` answered {answered.status_code} for an enrolled student inside "
        f"an open window. Body begins {answered.text[:300]!r}."
    )
    surface = response_surface(answered)
    assert str(world.enrolled_section_id) in surface, (
        "The answer names neither section, so it carries no submission because it carries nothing. "
        f"Body begins {answered.text[:300]!r}."
    )

    leaked = sorted(value for value in forbidden if value in surface)
    assert not leaked, (
        f"This student's own read carries {leaked}, which is a classmate's stored submission — "
        f"their comment, or the hours they reported. First occurrence: "
        f"{around(surface, leaked[0])!r}.\n\n"
        "SPEC §5.4: a student sees their own section and never another individual's raw data; §4 "
        "keys every response to its author. The student here has submitted nothing, so an answer "
        "carrying one has looked a submission up by section and week and forgotten whose it is — "
        "which is E2-05's uniqueness key with the student left out."
    )


def test_a_session_that_is_not_this_students_is_refused_exactly_as_no_session_is(
    student_read_door: StudentReadDoor,
) -> None:
    """The access half: this path answers a student, and refuses everybody else the same way.

    Two requests that must be refused — one carrying a session a real instructor
    landing issued, one carrying no session at all — and E2-09 settles that both
    get the same answer: `401`, `WWW-Authenticate: Bearer`, and the copy-registry
    detail. Same, because the difference between them is a fact about who is
    signed in, and a path that spells "you are signed in, but not as a student"
    differently from "you are not signed in" hands an enumerator the difference.

    **The mutations this kills:** a route that checks for a session and not for
    the role, which answers an instructor with a student's own answers; and a
    route that refuses the two cases differently — a `403` for the wrong role
    beside a `401` for none — which is the same disclosure as the 404-versus-403
    one above, one layer up.

    **The near miss it must survive** is the whole rest of this module: the same
    path, with a student's session, answers `200`. A door that refused everybody
    would satisfy this test and fail every other one here, which is why the two
    live in one module.

    **The anonymous case is measured twice, on either side of the instructor's
    launch, and that is `docs/disputes/E2-09-01.md`'s repair asserted rather than
    only arranged.** Minting the instructor's session drives a second launch,
    whose landing sets `pulse_session` in the same client's cookie jar — so in the
    first version of this test, where both refusals were built in one dict
    literal, the anonymous request ran second and carried the *instructor's*
    cookie. It was refused, the test passed, and what it measured was an
    instructor's session twice: once by header and once by cookie. The credential-
    free case was exercised nowhere in E2-09. `get_without_a_session` empties the
    jar now, and taking the anonymous reading before and after the launch is what
    says so out loud: two identical refusals mean the jar the launch filled
    changed nothing, and a difference between them means this test is measuring
    whatever a previous call left behind.
    """
    allowed = student_read_door.get()
    assert allowed.status_code == 200, (
        f"The student's own session was answered {allowed.status_code}, so the two refusals below "
        "would be equally well explained by a route that refuses everybody. Body begins "
        f"{allowed.text[:300]!r}."
    )

    # Taken before the instructor's launch fills the cookie jar, and again after.
    # The order is the subject here, so the three calls are separate statements
    # rather than values in one literal.
    anonymous_before = student_read_door.get_without_a_session()
    instructor_refusal = student_read_door.get_as_an_instructor()
    anonymous_after = student_read_door.get_without_a_session()

    assert (anonymous_before.status_code, anonymous_before.text) == (
        anonymous_after.status_code,
        anonymous_after.text,
    ), (
        f"A request carrying no credential was answered {anonymous_before.status_code} "
        f"{anonymous_before.text[:200]!r} before the instructor's launch and "
        f"{anonymous_after.status_code} {anonymous_after.text[:200]!r} after it. The launch sets "
        "`pulse_session` in this client's cookie jar, so a difference between the two means the "
        "second request is carrying that cookie — which is exactly the defect "
        "`docs/disputes/E2-09-01.md` found, and it makes whichever of these two readings runs "
        "second a measurement of somebody else's session rather than of an anonymous request."
    )

    refusals = {
        "an instructor's session": instructor_refusal,
        "no session at all": anonymous_after,
    }
    for what, answered in refusals.items():
        assert answered.status_code == REFUSED_STATUS, (
            f"`GET {STUDENT_READ_PATH}` with {what} was answered {answered.status_code}, not "
            f"{REFUSED_STATUS}. Body begins {answered.text[:300]!r}. E2-09's `require_student` "
            "refuses a role that is not `LandingRole.STUDENT` and an absent or invalid session "
            "with one answer."
        )
        assert AUTHENTICATE_SCHEME in (answered.headers.get(AUTHENTICATE_HEADER) or ""), (
            f"The refusal of {what} carries `{AUTHENTICATE_HEADER}: "
            f"{answered.headers.get(AUTHENTICATE_HEADER)!r}`, which does not name "
            f"`{AUTHENTICATE_SCHEME}`. The session travels as a Bearer token inside the "
            "third-party iframe (E1-08's cookieless path), so that is the scheme a 401 has to name."
        )

    instructor, anonymous = refusals["an instructor's session"], refusals["no session at all"]
    assert instructor.text == anonymous.text, (
        f"An instructor's session was refused with {instructor.text[:200]!r} and a request with no "
        f"session with {anonymous.text[:200]!r}. Two different refusals tell the caller that the "
        "first token was recognised — that it is a valid session for somebody, just not for a "
        "student — which is a fact about who holds it that a refusal has no business confirming."
    )

    world = student_read_door.world
    for what, answered in refusals.items():
        surface = response_surface(answered)
        named = sorted(
            value
            for value in {str(world.enrolled_section_id), world.subject}
            if value and value in surface
        )
        assert not named, (
            f"The refusal of {what} carries {named} — this student's own section, or the subject "
            f"their responses are keyed to. First occurrence: {around(surface, named[0])!r}. A "
            "refusal says no; it does not describe the person it is refusing on behalf of."
        )
