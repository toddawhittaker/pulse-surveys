"""`leadership_grant_covers` answers on the full leadership purview — E9-01, done-when 11.

> 11. `leadership_grant_covers` admits the assistant dean's launch into a section
>     of a supervised chair's department, and still refuses a lead's launch into
>     a sibling lead's course (the existing test stays green unchanged).

ADR 0108 built the predicate out of own grants because the union raised, and
recorded the consequence: "A person whose only leadership assignment is
`ASSISTANT_DEAN` never passes, and that is fail-closed until E9." The ticket
moves it onto the full leadership purview. The refusal half is
`test_the_leadership_grant_covers_no_sibling_leads_course.py`, unchanged; this
module adds the admission and its pair over the same assistant dean, so a
predicate that answers yes to everything in the college is red here too.

**The world** is §2.1's worked example in miniature: one college, a supervised
department S whose chair reports to the assistant dean, and an unsupervised
department U whose chair reports to the dean, holding the course the assistant
dean leads and one more course they do not.

**The call is bound by signature**, by `covers` copied from the existing module
for the reason that module gives: no record settles the parameter names, so the
grains are filled by name and a parameter this cannot fill fails naming it.

Rows are committed and read over `application_session` (`docs/MISTAKES.md`
entry 46).

**Which failure a red is, before E9-01 lands.** The admission test fails on its
assertion: the predicate answers no for every grain of S. The refusal pair is
green before and after; it is the control that keeps the admission honest.
"""

import inspect
from typing import Any

import pytest
from fixtures.purview_walk import written

pytestmark = [pytest.mark.integration, pytest.mark.invariant]

PREDICATE = "leadership_grant_covers"
GRAINS = ("section", "course", "prefix")
GRAIN_PARAMETERS = {
    "section": ("section_id", "section", "section_node_id"),
    "course": ("course_id", "course", "course_node_id"),
    "prefix": ("prefix_id", "prefix", "prefix_node_id"),
}
SESSION_PARAMETERS = ("session", "db", "db_session", "connection")
PERSON_PARAMETERS = ("person_id", "person")
ABOVE_A_COURSE = ("institution", "college", "department", "prefix", "term")


def covers(authz: Any, session: Any, *, person: Any, **grains: Any) -> Any:
    """Ask `leadership_grant_covers` about one context, filling only what it takes.

    A copy of `covers` in `test_the_leadership_grant_covers_no_sibling_leads_
    course.py`; see that module for why the call is bound by signature.
    """
    function = authz.symbol(PREDICATE)
    parameters = inspect.signature(function).parameters
    taken = {
        grain: name for grain in GRAINS for name in GRAIN_PARAMETERS[grain] if name in parameters
    }
    unknown = sorted(set(grains) - set(taken))
    assert (
        not unknown
    ), f"`{PREDICATE}` takes no parameter for {unknown}; it takes {list(parameters)}."

    positional: list[Any] = []
    keywords: dict[str, Any] = {}
    for parameter in parameters.values():
        if parameter.kind in (parameter.VAR_POSITIONAL, parameter.VAR_KEYWORD):
            continue
        if parameter.name in SESSION_PARAMETERS:
            value: Any = session
        elif parameter.name in PERSON_PARAMETERS:
            value = person
        elif parameter.name in set(taken.values()):
            value = grains.get(next(g for g, n in taken.items() if n == parameter.name))
        elif parameter.default is not parameter.empty:
            continue
        else:
            pytest.fail(f"`{PREDICATE}` requires `{parameter.name}`, which this test cannot fill.")
        if parameter.kind is parameter.POSITIONAL_ONLY:
            positional.append(value)
        else:
            keywords[parameter.name] = value
    return function(*positional, **keywords)


def node_id(rows: Any, chain: dict[str, Any], level: str) -> Any:
    return rows.graph.key_of(level, chain[level])


def the_worked_example(rows: Any) -> dict[str, Any]:
    """One college; department S supervised through the assistant dean, department U not."""
    graph = rows.graph
    key = graph.assignment_key
    graph.scope("section")
    college = graph.scope("college")
    supervised = graph.new_branch("institution", "college", "term")
    rows.seed("section", supervised)
    unsupervised = graph.new_branch("institution", "college", "term")
    rows.seed("section", unsupervised)
    led = {name: row for name, row in unsupervised.items() if name in ABOVE_A_COURSE}
    rows.seed("section", led)

    person = graph.person()
    dean = written(graph, lambda: graph.assign("DEAN", scope=college, reports_to=None), "The dean")
    assistant = written(
        graph,
        lambda: graph.assign("ASSISTANT_DEAN", scope=college, person=person, reports_to=dean[key]),
        "The assistant dean",
    )
    written(
        graph,
        lambda: graph.assign(
            "CHAIR", scope=node_id(rows, supervised, "department"), reports_to=assistant[key]
        ),
        "The chair of S, reporting to the assistant dean",
    )
    chair_u = written(
        graph,
        lambda: graph.assign(
            "CHAIR", scope=node_id(rows, unsupervised, "department"), reports_to=dean[key]
        ),
        "The chair of U, reporting straight to the dean",
    )
    led_course = node_id(rows, led, "course")
    written(
        graph,
        lambda: graph.lead_mapping(person=person, course=led_course),
        "The assistant dean's lead mapping",
    )
    written(
        graph,
        lambda: graph.assign(
            "LEAD_FACULTY", scope=led_course, person=person, reports_to=chair_u[key]
        ),
        "The assistant dean's lead assignment, under U's chair",
    )
    rows.commit()
    return {"person": person, "supervised": supervised, "unsupervised": unsupervised, "led": led}


def test_the_assistant_deans_launch_into_a_supervised_chairs_department_is_covered(
    authz: Any, committed_rows: Any, application_session: Any
) -> None:
    """The admission: every grain of a section in S answers yes for the assistant dean.

    S's chair reports to the assistant dean, so S's subtree — its prefix, its
    course and its section — is in the assistant dean's purview (SPEC §2.1), and
    ADR 0108's prefix-or-below test passes at each grain.

    **The mutations this kill:** the predicate still built over own grants (the
    assistant dean's own grant is empty, so it answers no — today's behaviour);
    the predicate built over the walk of the person's first leadership
    assignment only (the lead hat, which holds none of S).
    """
    rows = committed_rows
    world = the_worked_example(rows)
    s = world["supervised"]
    asked = {
        "section": covers(
            authz, application_session, person=world["person"], section=node_id(rows, s, "section")
        ),
        "course": covers(
            authz, application_session, person=world["person"], course=node_id(rows, s, "course")
        ),
        "prefix": covers(
            authz, application_session, person=world["person"], prefix=node_id(rows, s, "prefix")
        ),
        "all three": covers(
            authz,
            application_session,
            person=world["person"],
            section=node_id(rows, s, "section"),
            course=node_id(rows, s, "course"),
            prefix=node_id(rows, s, "prefix"),
        ),
    }
    refused = sorted(grain for grain, answer in asked.items() if not answer)
    assert not refused, (
        f"`{PREDICATE}` refused the assistant dean's launch into a supervised chair's department "
        f"at {refused} (it answered {asked}). The ticket: it 'uses the full leadership purview, "
        "so an assistant dean's launch into a supervised chair's department binds'."
    )


def test_the_assistant_deans_launch_into_an_unsupervised_department_beside_their_led_course_is_refused(
    authz: Any, committed_rows: Any, application_session: Any
) -> None:
    """The pair: a course in U that the assistant dean does not lead answers no at every grain.

    U holds the assistant dean's led course, under the same prefix, so a
    predicate that widened from the led course to its prefix or department —
    or that read the assistant dean's college scope — says yes here. The control
    is the led course itself, which answers yes.

    **The mutations this kill:** the assistant dean's grant read off the college;
    the lead grant widened to its prefix; `True` unconditionally.
    """
    rows = committed_rows
    world = the_worked_example(rows)
    u, led = world["unsupervised"], world["led"]
    person = world["person"]

    assert covers(authz, application_session, person=person, course=node_id(rows, led, "course")), (
        f"`{PREDICATE}` refused the course the assistant dean leads, so the refusals below are "
        "about a person the predicate admits nowhere."
    )
    assert node_id(rows, u, "prefix") == node_id(
        rows, led, "prefix"
    ), "The led course and the other course of U are not under one prefix; the world is broken."
    asked = {
        "section": covers(
            authz, application_session, person=person, section=node_id(rows, u, "section")
        ),
        "course": covers(
            authz, application_session, person=person, course=node_id(rows, u, "course")
        ),
        "prefix": covers(
            authz, application_session, person=person, prefix=node_id(rows, u, "prefix")
        ),
    }
    admitted = sorted(grain for grain, answer in asked.items() if answer)
    assert not admitted, (
        f"`{PREDICATE}` admitted the assistant dean into a course of the unsupervised department "
        f"at {admitted} (it answered {asked}). They lead one course there and supervise nobody "
        "in it; SPEC §2.1 gives them 'own led courses union every supervised chair's department'."
    )
