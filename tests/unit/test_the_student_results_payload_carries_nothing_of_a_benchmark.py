"""SPEC §4.1 item 1 over the student results payload, structurally — E7-02, done-when 7.

> **The sweep covers the route.** The invariant-marked student-route sweep reaches
> the new route and finds no comparison-set or university figure.

The route sweeps (`tests/integration/test_every_student_route_carries_nothing_of_a_
benchmark.py` and `test_the_student_read_path_names_nothing_outside_the_enrollment.py`)
drive the route; this is the structural half beside
`test_the_student_payload_schema_carries_nothing_of_a_benchmark.py`, which plants
on every model declared in `app.schemas.student`. The ticket lets the results
payload live in `app.schemas.response_loop` instead (its "Owns"), where that sweep
does not look — the enclosure one level out (`docs/MISTAKES.md` entry 53) — so
the two classes work order decision 4 names are found in either home and planted
on here.

**And their vocabularies are exactly decision 4's.** `state` admits the four
states and nothing else — `small-N` is E8's (ruling 8) — and `author_role` the
three roles a response is written under.

**The controls.** Each class must construct from its own declared members, so a
schema that refused everything cannot pass the refusals; the library's own
default for an unknown member is pinned by
`test_the_student_payload_schema_carries_nothing_of_a_benchmark.py`'s control and
not repeated here.

**The marker sits at module level**: this name carries `carries_nothing`.

**Which failure a red is, before E7-02 lands.** `the_payload_class` fails naming
both homes and the class.
"""

from datetime import UTC, datetime
from importlib import import_module
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

pytestmark = [pytest.mark.invariant]

SCHEMA_HOMES = ("app.schemas.response_loop", "app.schemas.student")
RESULTS_SCHEMA = "StudentWeekResults"
RESPONSE_SCHEMA = "StudentResponse"

STATES = ("awaiting", "published", "on-behalf", "unanswered")
# One level out: E8's state, a capitalised spelling, and a word the hold could be called.
NOT_STATES = ("small-N", "Awaiting", "held")
AUTHOR_ROLES = ("INSTRUCTOR", "LEAD_FACULTY", "CHAIR")
NOT_AUTHOR_ROLES = ("DEAN", "instructor")

# The amendment before review, A1: the published course weeks, on every payload.
PUBLISHED_WEEKS = "published_weeks"
WEEKS = [1, 2]

# E8-01's members, as a held week carries them (its work order): the course label
# always, and the streams, the workload median and the release group `None`.
# Passed explicitly on every construction here, so whether the builder gives the
# last three a default is not something this file decides (`docs/MISTAKES.md`
# entry 22: a new member reaches every fixture).
HELD_E8_01_MEMBERS: dict[str, Any] = {
    "course_label": "E7-02 BIO 101 F1WW — A course, Fall 2026",
    "streams": None,
    "workload_median": None,
    "released": None,
}

PLANTED_MEMBERS = ("benchmark", "comparison", "university_mean")
PLANTED_VALUE: dict[str, Any] = {"points": [{"course_week": 1, "mean": {"figure": 4.2}}]}

A_RESPONSE: dict[str, Any] = {
    "text": "E7-02 a response",
    "author_name": "E7-02 an author",
    "author_role": "INSTRUCTOR",
    "published_at": datetime(2026, 10, 12, 11, 0, tzinfo=UTC),
}


def the_payload_class(name: str) -> type[BaseModel]:
    """The one class called `name` declared in either home, or a failure naming both."""
    found: dict[str, type[BaseModel]] = {}
    for home in SCHEMA_HOMES:
        try:
            module = import_module(home)
        except ModuleNotFoundError:
            continue
        value = getattr(module, name, None)
        if isinstance(value, type) and issubclass(value, BaseModel) and value.__module__ == home:
            found[home] = value
    if len(found) != 1:
        pytest.fail(
            f"{len(found)} of {list(SCHEMA_HOMES)} declare a pydantic `{name}` ({sorted(found)}). "
            "E7-02's work order (decision 4, and A1) settles `StudentWeekResults {state, response, "
            "published_weeks}` and "
            "`StudentResponse {text, author_name, author_role, published_at}`, in one of the two."
        )
    return next(iter(found.values()))


def complaints_about(model: type[BaseModel], values: dict[str, Any], key: str) -> list[Any]:
    try:
        model(**values)
    except ValidationError as refused:
        return [error for error in refused.errors() if tuple(error.get("loc", ()))[:1] == (key,)]
    return []


def test_both_classes_construct_from_their_own_members() -> None:
    """The control: a held week and a published one both build.

    **A red here means these tests are broken, not the code** — or the members
    moved from decision 4's, which this control is the place to follow.
    """
    results = the_payload_class(RESULTS_SCHEMA)
    response = the_payload_class(RESPONSE_SCHEMA)

    held = results(state="awaiting", response=None, published_weeks=WEEKS, **HELD_E8_01_MEMBERS)
    released = results(
        state="published",
        response=response(**A_RESPONSE),
        published_weeks=WEEKS,
        **HELD_E8_01_MEMBERS,
    )

    assert held.state == "awaiting" and held.response is None
    assert released.response is not None and released.response.text == A_RESPONSE["text"]


def test_the_results_payload_declares_the_published_weeks() -> None:
    """The amendment's A1: `StudentWeekResults` carries `published_weeks`, on every state.

    **The mutation this kills:** the list put somewhere the page cannot read with
    the week (a separate route, an optional member left out of the closed states),
    so the page has nothing to page through on a held week.
    """
    results = the_payload_class(RESULTS_SCHEMA)

    assert PUBLISHED_WEEKS in results.model_fields, (
        f"`{RESULTS_SCHEMA}` declares {sorted(results.model_fields)}; the amendment's A1 adds "
        f"`{PUBLISHED_WEEKS}: list[int]`."
    )
    held = results(state="awaiting", response=None, published_weeks=WEEKS, **HELD_E8_01_MEMBERS)
    assert held.published_weeks == WEEKS


@pytest.mark.parametrize("planted", PLANTED_MEMBERS)
@pytest.mark.parametrize("which", [RESULTS_SCHEMA, RESPONSE_SCHEMA])
def test_a_planted_benchmark_member_is_refused_by_the_results_payload(
    which: str, planted: str
) -> None:
    """A member the class never declared, carrying a benchmark shape, is refused by name.

    **What is asserted is a complaint about the planted key**, built on a
    payload that is otherwise whole, so the refusal cannot be about a missing
    member (`docs/MISTAKES.md` entry 3).

    **The mutation this kills:** the payload left at pydantic's default
    `extra="ignore"`, under which a service passing a comparison figure has it
    dropped in silence today and served the day the class grows the member.
    """
    model = the_payload_class(which)
    whole: dict[str, Any] = (
        {"state": "awaiting", "response": None, PUBLISHED_WEEKS: WEEKS, **HELD_E8_01_MEMBERS}
        if which == RESULTS_SCHEMA
        else dict(A_RESPONSE)
    )

    complaints = complaints_about(model, {**whole, planted: PLANTED_VALUE}, planted)

    assert complaints, (
        f"`{which}` accepted a member called `{planted}` it does not declare. SPEC §4.1 item 1 and "
        "§5.4: a student payload carries no comparison, benchmark or university figure, and a "
        "schema that drops an unknown member is one service change away from carrying one."
    )


@pytest.mark.parametrize("state", STATES)
def test_each_of_the_four_states_is_admitted(state: str) -> None:
    """Decision 3's four states construct. **The mutation this kills:** a state left out.

    Each is built the way decision 4 pairs it: no response for the two closed
    states, a response for the two released ones.
    """
    results = the_payload_class(RESULTS_SCHEMA)
    response = the_payload_class(RESPONSE_SCHEMA)
    carried = None if state in ("awaiting", "unanswered") else response(**A_RESPONSE)

    built = results(state=state, response=carried, published_weeks=WEEKS, **HELD_E8_01_MEMBERS)
    assert built.state == state


@pytest.mark.parametrize("state", NOT_STATES)
def test_a_state_outside_the_four_is_refused(state: str) -> None:
    """`small-N` (E8's), a capitalised spelling, and `held`: refused.

    **The mutation this kills:** `state: str`, under which any spelling a service
    produces reaches the page, and the page's closed door keys on a string nobody
    checked.
    """
    results = the_payload_class(RESULTS_SCHEMA)

    complaints = complaints_about(
        results,
        {"state": state, "response": None, PUBLISHED_WEEKS: WEEKS, **HELD_E8_01_MEMBERS},
        "state",
    )

    assert complaints, f"`{RESULTS_SCHEMA}` admitted the state {state!r}; decision 4: four states."


@pytest.mark.parametrize("role", NOT_AUTHOR_ROLES)
def test_an_author_role_outside_the_three_is_refused(role: str) -> None:
    """`DEAN` and a lower-case spelling: refused. The three roles are the writer's vocabulary.

    **The mutation this kills:** `author_role: str`.
    """
    response = the_payload_class(RESPONSE_SCHEMA)

    complaints = complaints_about(response, {**A_RESPONSE, "author_role": role}, "author_role")

    assert (
        complaints
    ), f"`{RESPONSE_SCHEMA}` admitted the role {role!r}; decision 4: {AUTHOR_ROLES}."
