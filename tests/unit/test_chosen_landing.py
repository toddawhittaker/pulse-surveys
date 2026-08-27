"""The landing a set of assignments chooses — ticket E1-13, the pure half.

E1-13 replaces `backend/app/services/landing.py`'s claims-derived mapping with a
resolution from the assignment model, and the work order splits it in two:
`resolve_landing` does the reads, and `chosen_landing(roles, *, enrolled_today,
door)` decides. This module is the second half — no database, no application, no
door — because every rule worth pinning is expressible over a set of roles, a
boolean and a door, and a rule pinned here fails with the input that broke it
rather than with a redirect that went somewhere unexpected.

**What the ticket says these rules are.** Criterion 4: "if precedence survives:
the two-role fixture person exists and the ordering test fails when the ordering
flips (proven by mutation)". The carried entry (`docs/tickets/e1/carried-from-e0.md`,
second entry) is what makes that criterion exist at all: `landing.py` carried two
orderings that were "written down but not held by any test, which was measured
rather than assumed — reversing both orderings leaves the whole unit suite and
both door suites green (424 tests, 2026-08-21)". So the ordering is pinned twice
here — once as the recorded tuple, once through the function that reads it —
and again, over rows and a real door, in
`tests/integration/test_landing_resolves_from_assignments.py`.

**Every name below is the settled contract rather than a discovery.** The work
order names `Door`, `LandingRole`, `LANDING_FOR_ROLE`, `LANDING_PRECEDENCE`,
`chosen_landing` and `resolve_landing` in `app.services.authz` before any of it
is written, so a name this module cannot find is a missing deliverable and not a
rename to accommodate here. They are reached through the `authz` fixture, which
turns an absent module or an absent symbol into a failed assertion instead of a
collection error: an import error is not a red, and a module that will not import
takes every test in the file down with it rather than reporting which criterion
nobody has met.

**The expected precedence is written down here, not read out of the module.**
`LANDING_PRECEDENCE` is the thing under test, so a test that derived its
expectation from it would agree with a reversed tuple exactly as happily as with
the right one — which is `docs/MISTAKES.md` entry 19, and is the precise shape the
carried entry measured. What is written below is the work order's own decision
(D2): leadership, then instructor, then care, then admin, assignments before
enrollment.

**The environment** (`docs/MISTAKES.md` entry 40): every test here depends on
`authz`, which depends on `configured_env`, so the documented variables have
values before `app.services.authz` is imported — that module builds nothing out
of `Settings` at import today, and a test that relied on it never doing so would
be resting on a property nobody stated.
"""

import importlib
import inspect
from typing import Any

import pytest

# `authz` comes from `tests/fixtures/authz_data.py` and `landing_contract` from
# `tests/fixtures/landing.py`; both are reached as fixtures rather than imported,
# for the reason this suite gives everywhere: an import of a fixtures module by
# name depends on where pytest put `tests/` on `sys.path`.

# Where `AssignmentRole` and `LEADERSHIP_ROLES` might be reachable from, most
# likely first. E0-11 types `guard_write`'s second parameter with the enum and no
# ticket says which module defines it, so it is looked for rather than imported
# under a path this file would be choosing —
# `tests/unit/test_lms_owned_writes_are_refused_at_the_chokepoint.py` makes the
# same lookup for the same reason. The chokepoint itself is tried first, since
# E1-13's `LANDING_FOR_ROLE` has to name the type to be annotated with it.
ROLE_ENUM_HOLDERS = ("app.models", "app.models.identity")

# The work order's decision D2, transcribed: "One total ordering at both doors:
# leadership > instructor > care > admin, assignments before enrollment." Written
# here rather than read off `LANDING_PRECEDENCE`, because that tuple is what these
# tests exist to hold — see this module's docstring.
EXPECTED_PRECEDENCE = ("LEADERSHIP", "INSTRUCTOR", "CARE", "ADMIN")

# The landing that is *not* in the ordering, and deliberately: a student holds no
# assignment at all (ADR 0028), so `STUDENT` is the enrollment fallback rather
# than a member of the precedence, consulted only when no assignment lands.
STUDENT_LANDING = "STUDENT"

# The signature `chosen_landing` is settled with. Asserted as a set, because the
# thing worth holding is that it takes **no session and no settings** — a
# parameter this suite could hand a database connection to is the difference
# between a decision and a read, and the work order puts the reads in
# `resolve_landing`.
CHOSEN_LANDING_PARAMETERS = {"roles", "enrolled_today", "door"}

# A value no `AssignmentRole` is, used for the fail-closed pair. The work order:
# "A ninth `AssignmentRole` member absent from this mapping contributes **no**
# landing (skipped, fail closed) — same shape as `_OWN_GRANT_ROOT` and ADR 0026's
# positive door lists."
A_ROLE_NOTHING_MAPS = "E1_13_A_ROLE_NO_MAPPING_NAMES"


def role_enum(authz: Any) -> Any:
    """`AssignmentRole`, wherever it lives, or a failure naming where it was looked for."""
    holders: list[Any] = [authz.module]
    for holder in ROLE_ENUM_HOLDERS:
        try:
            holders.append(importlib.import_module(holder))
        except ImportError:
            continue
    for module in holders:
        found = getattr(module, "AssignmentRole", None)
        if found is not None:
            return found
    pytest.fail(
        f"Neither the chokepoint nor {list(ROLE_ENUM_HOLDERS)} exposes an `AssignmentRole`. "
        "E1-13's `LANDING_FOR_ROLE` is a mapping keyed by that enum, so it has to be reachable "
        "from somewhere a caller can import it. If it is spelled differently or lives elsewhere, "
        "say so in the pull request; `ROLE_ENUM_HOLDERS` in this file is the one line that changes."
    )


def leadership_roles(authz: Any) -> tuple[Any, ...]:
    """`LEADERSHIP_ROLES`, wherever it lives, as a tuple.

    SPEC §2.1's reporting chain above the instructor — lead faculty, chair,
    assistant dean, dean, VP of academics — collected in one place so that "these
    five share one view" is a fact about the enumeration rather than a list this
    file typed out. `docs/MISTAKES.md` entry 19: an expectation held in a copy of
    the thing it checks agrees with the copy.
    """
    holders: list[Any] = [authz.module]
    for holder in ROLE_ENUM_HOLDERS:
        try:
            holders.append(importlib.import_module(holder))
        except ImportError:
            continue
    for module in holders:
        found = getattr(module, "LEADERSHIP_ROLES", None)
        if found:
            return tuple(found)
    pytest.fail(
        f"Neither the chokepoint nor {list(ROLE_ENUM_HOLDERS)} exposes a non-empty "
        "`LEADERSHIP_ROLES`. E0-11 collects SPEC §2.1's reporting chain there and E1-13's "
        "`LANDING_FOR_ROLE` maps every one of its members onto the one leadership view."
    )


def landing_named(authz: Any, contract: Any, name: str) -> Any:
    """One `LandingRole` member by its member name, or a failure saying it is absent.

    Member names rather than values, because `verified_session` reads
    `LandingRole[...]` by member name — the work order's own trap note — so the
    names are the part of the enum that cannot move in E1-13's file-to-file
    migration.
    """
    enumeration = authz.symbol(contract.landing_role_enum)
    member = getattr(enumeration, name, None)
    assert member is not None, (
        f"`{contract.authz_module}.{contract.landing_role_enum}` has no `{name}` member; it has "
        f"{[found.name for found in enumeration]}. E1-13 moves this enum out of the deleted "
        "`app/services/landing.py` with its **member names unchanged**, because "
        "`verified_session` reads `LandingRole[...]` by name and every session issued before the "
        "move has to keep verifying."
    )
    return member


def a_role_landing_on(authz: Any, contract: Any, landing_name: str) -> Any:
    """Some `AssignmentRole` the landing map sends to the landing called `landing_name`.

    The *input* is discovered and the *expectation* is written down, which is the
    split this module rests on: which assignment role produces a leadership
    landing is a detail of `LANDING_FOR_ROLE` and is asserted on its own below,
    while the order those landings are chosen in is the work order's decision and
    is transcribed at the top of this file.
    """
    mapping = authz.symbol(contract.landing_for_role)
    wanted = landing_named(authz, contract, landing_name)
    for role, landing in mapping.items():
        if landing is wanted:
            return role
    pytest.fail(
        f"`{contract.landing_for_role}` maps no assignment role onto {landing_name}; it maps "
        f"{ {getattr(role, 'name', role): getattr(landing, 'name', landing) for role, landing in mapping.items()} }. "
        "Every member of `LANDING_PRECEDENCE` has to be reachable from some role, or the ordering "
        "has an entry no person can ever hold and the pins below are about a case that cannot "
        "arise."
    )


# ---------------------------------------------------------------------------
# The map: every role has a view, and the five leadership roles share one.
# ---------------------------------------------------------------------------


def test_every_assignment_role_the_schema_enumerates_has_a_landing(
    authz: Any, landing_contract: Any
) -> None:
    """Criterion 1's precondition: no role the database can hold is a person with no view.

    E1-13's scope: "every other role acts through a live assignment", and §2.1's
    table gives each of the eight a view. A role the map does not name contributes
    no landing — that is the fail-closed rule the work order settles for a *ninth*
    member somebody adds later — so a role that exists today and is missing here
    is a live person who can hold an assignment, pass every door check, and be
    told there is nothing for them.

    **Dies if any of the eight is dropped from the map.** The set is compared
    whole rather than probed member by member, so the failure names exactly which
    role has no view.

    **Its non-vacuity guard is the enum itself**: an `AssignmentRole` with no
    members would make "every member is mapped" true of a mapping that is empty
    (`docs/MISTAKES.md` entry 3).
    """
    roles = list(role_enum(authz))
    assert roles, (
        "`AssignmentRole` enumerates no members at all, so 'every role has a landing' is true of "
        "an empty mapping. ADR 0028 gives it eight — every row of SPEC §2.1's table except "
        "Student, which holds no assignment."
    )

    mapping = authz.symbol(landing_contract.landing_for_role)
    unmapped = sorted(role.name for role in roles if role not in mapping)

    assert not unmapped, (
        f"`{landing_contract.landing_for_role}` names no landing for {unmapped}. It maps "
        f"{sorted(getattr(role, 'name', str(role)) for role in mapping)}, and `AssignmentRole` "
        f"enumerates {sorted(role.name for role in roles)}. An unmapped role contributes no "
        "landing by design — which is right for a member added by a later migration and wrong for "
        "one that exists now: SPEC §2.1's table gives every one of these a view, so a person "
        "holding this assignment would be met with the no-access page."
    )


def test_the_five_leadership_roles_all_land_on_the_one_leadership_view(
    authz: Any, landing_contract: Any
) -> None:
    """SPEC §2.1's reporting chain above the instructor reaches one screen, not five.

    E1-04 gives this application five route groups, and §2 gives leadership one of
    them: a dean, a chair, an assistant dean, a lead faculty member and a VP of
    academics differ in *purview*, which E9 computes, and not in which view they
    land on.

    **Dies if any one of the five is mapped somewhere else** — mapping `CHAIR` to
    the instructor view, say, which is the plausible edit for somebody who reads
    "a chair can also lead courses" as "a chair teaches".

    The five come from `LEADERSHIP_ROLES` rather than from a list typed here, so
    a sixth leadership role added to that enumeration is covered the day it lands
    rather than the day somebody remembers this file.
    """
    leadership = leadership_roles(authz)
    mapping = authz.symbol(landing_contract.landing_for_role)
    expected = landing_named(authz, landing_contract, "LEADERSHIP")

    wrong = {
        role.name: getattr(mapping.get(role), "name", mapping.get(role))
        for role in leadership
        if mapping.get(role) is not expected
    }

    assert not wrong, (
        f"These members of `LEADERSHIP_ROLES` do not land on the leadership view: {wrong}. SPEC §2 "
        "gives leadership one entry point and one view; what separates a chair from a dean is the "
        "purview E9 computes over the supervision graph, not the screen they arrive at."
    )


def test_the_landing_map_never_names_the_student_view(authz: Any, landing_contract: Any) -> None:
    """ADR 0028, at the mapping: a student holds no assignment, so no assignment lands student.

    "A student holds no `role_assignment` row, and one cannot be written: the enum
    has no label for it." The student landing exists and is reached from
    `enrollment` alone — which is the whole of what makes E1-13's launch door ask
    two questions rather than one.

    **Dies if somebody maps a role onto the student view** to "make the fallback
    simpler", which would give a real assignment a student's screen and, worse,
    put a student's landing inside the precedence where an assignment could lose
    to it.
    """
    mapping = authz.symbol(landing_contract.landing_for_role)
    student = landing_named(authz, landing_contract, STUDENT_LANDING)

    naming_student = sorted(
        getattr(role, "name", str(role)) for role, landing in mapping.items() if landing is student
    )

    assert not naming_student, (
        f"`{landing_contract.landing_for_role}` maps {naming_student} onto the student view. ADR "
        "0028: a student's access is resolved from `enrollment` — 'the LMS-owned, term-windowed "
        "record of which sections the person is in' — and never from an assignment, because a "
        "role assignment carries no window and no roster sync corrects it."
    )


# ---------------------------------------------------------------------------
# The recorded ordering. Criterion 4, twice: as the tuple, and through the
# function that reads it.
# ---------------------------------------------------------------------------


def test_the_recorded_precedence_is_the_ordering_the_work_order_decided(
    authz: Any, landing_contract: Any
) -> None:
    """Criterion 4's first half: the ordering is written down, by name, in one place.

    The carried entry measured that `landing.py`'s two orderings were held by
    nothing — "reversing both orderings leaves the whole unit suite and both door
    suites green (424 tests, 2026-08-21)". This is the assertion whose absence that
    measurement found.

    **Dies on any reordering at all**, including the single transposition a pair
    test could miss: the whole sequence is compared, in order, against the
    decision recorded at the top of this file rather than against the tuple under
    test.

    **`STUDENT` is asserted absent as well as the four being present.** The
    enrollment fallback is consulted only when no assignment lands (work order
    D3), so a student landing inside the precedence would let a staff member who
    is also enrolled lose their staff view to their student one — which is the
    exact ordering decision D2 makes in the other direction.
    """
    precedence = authz.symbol(landing_contract.landing_precedence)
    names = [getattr(member, "name", str(member)) for member in precedence]

    assert names == list(EXPECTED_PRECEDENCE), (
        f"`{landing_contract.landing_precedence}` is {names} and the ordering E1-13 records is "
        f"{list(EXPECTED_PRECEDENCE)}. SPEC §2 says a launch shows the full purview rather than "
        "the launch context, so the higher-standing hat's screen is the useful one; "
        "leadership-over-Care-over-admin is E0-18's own recorded intent, which nothing has held "
        "until now. If the ordering is being *changed* rather than broken, the ADR E1-13 writes "
        "is what changes and this transcription follows it."
    )
    assert STUDENT_LANDING not in names, (
        f"`{landing_contract.landing_precedence}` carries {STUDENT_LANDING}. Student is the "
        "enrollment fallback, reached only when no assignment lands: inside the ordering it "
        "becomes something an assignment can lose to, and a teaching assistant enrolled in the "
        "course she grades would land on her own results page."
    )


@pytest.mark.parametrize(
    ("higher", "lower"),
    [
        (higher, lower)
        for index, higher in enumerate(EXPECTED_PRECEDENCE)
        for lower in EXPECTED_PRECEDENCE[index + 1 :]
    ],
)
@pytest.mark.parametrize("order", ("higher first", "lower first"))
def test_a_person_holding_two_roles_lands_on_the_higher_of_the_two(
    authz: Any, landing_contract: Any, higher: str, lower: str, order: str
) -> None:
    """Criterion 4 through the function: every ordered pair, in both input orders.

    Six pairs over four landings, each posed twice, so no single transposition of
    `LANDING_PRECEDENCE` survives: swapping only care and admin leaves leadership
    above instructor and would pass a test that checked the extremes.

    **The input order is a parameter for a reason.** A function that answered
    "whichever role came first in the collection" is right half the time and would
    pass every one-order test in this file — and it is what `max(...)` over an
    unordered set, or a `for role in roles: return LANDING_FOR_ROLE[role]`, both
    produce. The collection handed in is a `frozenset` in neither case: it is a
    list, built in the order the parameter names, because the work order types the
    parameter `Collection[AssignmentRole]` and a set would hide the question.

    **Dies if `LANDING_PRECEDENCE` is reversed** (the carried entry's own
    mutation), **dies on any adjacent swap**, and **dies if the function ignores
    the ordering and reads the collection's order instead.**
    """
    chosen = authz.symbol(landing_contract.chosen_landing)
    door = authz.symbol(landing_contract.door_enum)
    higher_role = a_role_landing_on(authz, landing_contract, higher)
    lower_role = a_role_landing_on(authz, landing_contract, lower)
    assert higher_role is not lower_role, (
        f"The landing map sends one assignment role — {getattr(higher_role, 'name', higher_role)!r}"
        f" — to both {higher} and {lower}, so no person can hold one of each and this pair cannot "
        "be posed."
    )
    held = [higher_role, lower_role] if order == "higher first" else [lower_role, higher_role]

    answered = chosen(held, enrolled_today=False, door=door.WEB)

    assert getattr(answered, "name", answered) == higher, (
        f"A person holding {[getattr(role, 'name', role) for role in held]} was landed on "
        f"{getattr(answered, 'name', answered)!r}; the recorded ordering puts {higher} above "
        f"{lower}. The roles were handed over {order}, so an answer that follows the collection "
        "rather than `LANDING_PRECEDENCE` fails on one of this test's two cases and passes the "
        "other — which is what makes both worth running."
    )


# ---------------------------------------------------------------------------
# The door's part, and the part that is deliberately not the door's.
# ---------------------------------------------------------------------------


def test_chosen_landing_takes_no_session_and_no_settings(authz: Any, landing_contract: Any) -> None:
    """The split the work order draws: this half decides, the other half reads.

    `chosen_landing(roles, *, enrolled_today, door)` and nothing else. The
    parameter list is the whole assertion, and it is worth one test because the
    tempting shape is the opposite one — a single function that takes a session
    and answers a landing, at which point the ordering is only reachable through a
    database and criterion 4's mutation proof needs rows.

    **Dies if a session, a connection or a `Settings` is added to the signature**,
    which is also how ADR 0013's threadpool rule would quietly stop applying to
    the half that does the IO.
    """
    chosen = authz.symbol(landing_contract.chosen_landing)
    parameters = set(inspect.signature(chosen).parameters)

    assert parameters == CHOSEN_LANDING_PARAMETERS, (
        f"`{landing_contract.chosen_landing}` takes {sorted(parameters)}; E1-13 settles it as "
        f"{sorted(CHOSEN_LANDING_PARAMETERS)}. The reads — the assignments filtered by the door's "
        "permission column, and the enrollment predicate — belong to `resolve_landing`, which is "
        "the function ADR 0013's threadpool rule is about."
    )


def test_the_roles_handed_in_are_taken_as_the_doors_answer_and_not_re_derived(
    authz: Any, landing_contract: Any
) -> None:
    """ADR 0026's rule has one authority, and it is the generated column.

    The work order settles it: `roles` is "the set of roles on the person's live
    assignments **already filtered by the entered door's permission column** (the
    SQL does the filtering; this function never re-derives door rules)". So a Care
    role reaching this function at the launch door is a Care landing — because the
    only way it could have got here is a `permits_launch` that said yes, and ADR
    0026 makes that column derived from the role so that no write path can
    contradict it.

    **Dies if the door rules are written a second time in Python** — a
    `if door is Door.LAUNCH: skip CARE` added here for safety. That is
    `docs/MISTAKES.md` entry 13's shape in the direction nobody notices: two
    copies of one rule, of which only one is the authority, and the day they
    disagree the column says one thing and the code does another. The behavioural
    half — that a Care assignment really is unreachable from a launch, by data —
    is asserted over a live door and real rows in
    `tests/integration/test_landing_resolves_from_assignments.py`, which is where
    the guarantee actually lives.
    """
    chosen = authz.symbol(landing_contract.chosen_landing)
    door = authz.symbol(landing_contract.door_enum)
    care_role = a_role_landing_on(authz, landing_contract, "CARE")

    answered = chosen([care_role], enrolled_today=False, door=door.LAUNCH)

    assert getattr(answered, "name", answered) == "CARE", (
        f"A Care role handed to this function at the launch door produced "
        f"{getattr(answered, 'name', answered)!r}. The filtering is ADR 0026's column's job and "
        "this function's contract is to take the filtered set as given: a second copy of the door "
        "rule here is a rule with two authorities, and the one an operator can read off the row is "
        "the one that stops being consulted."
    )


def test_the_enrollment_fallback_answers_student_at_the_launch_door_only(
    authz: Any, landing_contract: Any
) -> None:
    """§2.1's "students enter by launch only", as the one door the fallback applies at.

    Three cases, and they are three because each kills a different mutation:
    an enrolled person with no assignment lands student at a launch; the same
    person at the web door lands nothing, because §2.1's table gives the student
    row one entry point; and an unenrolled person with no assignment lands nothing
    at either.

    **Dies if the door check is dropped** — the web case starts answering student,
    which would give anybody with an old enrollment a way in through a door §2.1
    does not give them. **Dies if `enrolled_today` is ignored** — the third case
    starts answering student, which is the calm no-access page turning into a
    student view for a person Pulse holds nothing about.
    """
    chosen = authz.symbol(landing_contract.chosen_landing)
    door = authz.symbol(landing_contract.door_enum)

    at_launch = chosen([], enrolled_today=True, door=door.LAUNCH)
    at_web = chosen([], enrolled_today=True, door=door.WEB)
    unenrolled = chosen([], enrolled_today=False, door=door.LAUNCH)

    assert getattr(at_launch, "name", at_launch) == STUDENT_LANDING, (
        f"An enrolled person holding no assignment was landed on {at_launch!r} at the launch door. "
        "ADR 0028 makes enrollment the whole of a student's access, and SPEC §2.1's table gives "
        "the Student row the LTI launch as its entry point."
    )
    assert at_web is None, (
        f"An enrolled person holding no assignment was landed on {at_web!r} at the web door. SPEC "
        "§2.1's table is authoritative on doors and gives students one: 'students enter by launch "
        "only'. A student who reached the web login has no view here, and the honest answer is the "
        "calm page rather than their results."
    )
    assert unenrolled is None, (
        f"A person with no assignment and no live enrollment was landed on {unenrolled!r}. E1-13's "
        "scope: 'A person with no assignment and no enrollment gets the calm no-access state.'"
    )


def test_an_assignment_is_chosen_over_the_enrollment_fallback(
    authz: Any, landing_contract: Any
) -> None:
    """D2's second half: "staff who are also enrolled act as staff".

    The teaching assistant the carried entry names — enrolled as a learner in the
    course she grades, and holding an instructor assignment for it. The carried
    entry says this rule was in `landing.py` and held by nothing: "Instructor beats
    Learner on a launch… No seeded launch carries both roles."

    **Dies if the enrollment predicate is consulted first**, which is the natural
    way to write it once the launch door has a `user_id` in hand and is cheaper to
    read than the assignment query. Under that order she lands on her own results
    page and her section's report is somewhere she has to go looking for it.
    """
    chosen = authz.symbol(landing_contract.chosen_landing)
    door = authz.symbol(landing_contract.door_enum)
    instructor_role = a_role_landing_on(authz, landing_contract, "INSTRUCTOR")

    answered = chosen([instructor_role], enrolled_today=True, door=door.LAUNCH)

    assert getattr(answered, "name", answered) == "INSTRUCTOR", (
        f"A person holding an instructor assignment *and* a live enrollment was landed on "
        f"{getattr(answered, 'name', answered)!r} at the launch door. E1-13 records assignments "
        "before enrollment: the enrollment fallback exists for the person who holds no assignment "
        "at all, and consulting it first hands a teaching assistant her own student view instead "
        "of the section she grades."
    )


# ---------------------------------------------------------------------------
# Fail closed, both directions.
# ---------------------------------------------------------------------------


def test_a_role_the_landing_map_does_not_name_contributes_no_landing(
    authz: Any, landing_contract: Any
) -> None:
    """The work order's fail-closed rule, posed with a value nothing maps.

    "A ninth `AssignmentRole` member absent from this mapping contributes **no**
    landing (skipped, fail closed) — same shape as `_OWN_GRANT_ROOT` and ADR 0026's
    positive door lists." ADR 0026's own consequences say why the lists are
    positive: "adding a role to the enum without adding it to a door list gives
    that role no door at all, which fails closed and reports itself the first time
    somebody tries to enter. That is the reason each list is positive: the
    negative spelling would hand a new role web login by default, from a line
    nobody revisited."

    **Dies against a default** — a `LANDING_FOR_ROLE.get(role, LandingRole.STUDENT)`
    or an `else` arm — which is how an unmapped role ends up on whichever screen
    came last in somebody's `if`.

    A `KeyError` escaping here is the same finding wearing a traceback: a lookup
    that raises on an unknown role turns a migration nobody finished into a 500 on
    a real person's launch. Its pair is the next test, which is what keeps this one
    from being satisfied by a function that answers `None` to everything.
    """
    chosen = authz.symbol(landing_contract.chosen_landing)
    door = authz.symbol(landing_contract.door_enum)
    mapping = authz.symbol(landing_contract.landing_for_role)
    assert A_ROLE_NOTHING_MAPS not in mapping, (
        f"`{landing_contract.landing_for_role}` names {A_ROLE_NOTHING_MAPS!r}, which this file "
        "invented precisely so that nothing would. Choose another sentinel."
    )

    answered = chosen([A_ROLE_NOTHING_MAPS], enrolled_today=False, door=door.WEB)

    assert answered is None, (
        f"A role no landing map names produced {answered!r}. The mapping is the whole of what "
        "turns an assignment into a view, and a role outside it is a role somebody added to the "
        "enum and did not finish wiring — which has to report itself as no view rather than as "
        "whichever view a default names."
    )


def test_an_unmapped_role_beside_a_mapped_one_leaves_the_mapped_one_standing(
    authz: Any, landing_contract: Any
) -> None:
    """The pair to the test above: the unknown role is skipped, not fatal.

    Without this, "an unmapped role contributes no landing" is equally satisfied
    by a function that answers `None` whenever it meets one — which would take a
    dean's landing away on the day somebody adds a ninth role to the enum and
    gives it to her as a second hat.

    **Dies if the unknown role short-circuits the whole answer**, and dies if it
    raises: the person here holds a real, mapped, live assignment and is owed the
    view it names.
    """
    chosen = authz.symbol(landing_contract.chosen_landing)
    door = authz.symbol(landing_contract.door_enum)
    admin_role = a_role_landing_on(authz, landing_contract, "ADMIN")

    answered = chosen([A_ROLE_NOTHING_MAPS, admin_role], enrolled_today=False, door=door.WEB)

    assert getattr(answered, "name", answered) == "ADMIN", (
        f"A person holding an administrator assignment beside a role nothing maps was landed on "
        f"{getattr(answered, 'name', answered)!r}. Skipping the unknown role is the fail-closed "
        "rule; discarding the whole answer because of it is a different rule, and it takes a real "
        "view away from a person who holds it."
    )


# ---------------------------------------------------------------------------
# Criterion 3 — the claims-derived mapping is gone, and its vocabulary moved.
# ---------------------------------------------------------------------------


def test_the_claims_derived_landing_module_no_longer_exists(landing_contract: Any) -> None:
    """Criterion 3, half of it: "`landing.py` and the EXCEPTIONS entry are gone".

    The carried entry's done-when: "the claims-derived mapping is **gone** — the
    landing view comes from the assignment model". A module left in place beside
    the new resolution is two answers to "what may this session act as", and the
    one nothing calls is the one that stops being reviewed.

    **Dies while the module is still importable**, which is HEAD. The other half —
    the exception it holds in the Care sweep — is asserted by
    `tests/unit/test_care_is_not_reachable_from_a_claim.py`, whose `EXCEPTIONS`
    equality is the signal the carried entry names as the sign this is finished.
    """
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module(landing_contract.retired_module)


def test_the_lis_vocabulary_is_reachable_from_the_launch_module(landing_contract: Any) -> None:
    """The vocabulary moves to the module SPEC §13 gives role resolution to (D7).

    `landing.py` is deleted, and the LIS names it held — the roles claim, the
    membership vocabulary, the two role URIs and `stated_roles` — are read by
    §7.3's provisioning and by the roster sync, which are lawful readers of a
    roles claim and are not this ticket's subject (D11). §13's comment for
    `app/lti/launch.py` is "launch validation, role/context resolution", so that
    is where they land.

    **Dies if the names are deleted along with the module they lived in**, which
    would take `provision_from_launch`'s staff test with them, and dies if they
    are scattered — one importable home is what keeps
    `tests/unit/test_care_is_not_reachable_from_a_claim.py`'s sweep able to say
    which modules read a claim at all.
    """
    try:
        module = importlib.import_module(landing_contract.launch_module)
    except ModuleNotFoundError as missing:  # pragma: no cover - a red, not a branch
        pytest.fail(
            f"`{landing_contract.launch_module}` does not import ({missing}). E1-08 builds the "
            "launch door there and E1-13 moves the LIS role vocabulary into it."
        )

    absent = [
        name for name in landing_contract.launch_vocabulary_names if not hasattr(module, name)
    ]

    assert not absent, (
        f"`{landing_contract.launch_module}` exposes none of {absent}; it exposes "
        f"{sorted(n for n in vars(module) if not n.startswith('_'))}. E1-13 deletes "
        f"`{landing_contract.retired_module}` and moves these there, because §7.3's provisioning "
        "and E1-11's roster sync both read the roles claim lawfully and need somewhere to import "
        "it from."
    )


# ---------------------------------------------------------------------------
# The calm page, and the property that makes it safe to render.
# ---------------------------------------------------------------------------


def test_the_no_access_page_takes_no_argument(
    landing_contract: Any, configured_env: dict[str, str]
) -> None:
    """D5's security property, as a signature: the page cannot repeat anything it was handed.

    `no_access()` "takes no argument (same security property as `cancelled_page`),
    names nobody, repeats nothing from any token". A page built from constants
    cannot be made to echo an attacker-chosen string, and the parameter list is
    where that is decidable rather than argued: `test_a_refusal_does_not_name_the_
    key_set_address_the_tool_could_not_reach` and E1-09's error-branch tests are
    the record of what an echoing page costs.

    **Dies if the page grows a `reason` parameter** — which is precisely the shape
    it replaces: `landing_with_session` loses its `no_role_reason`, and a page that
    took one back would be that parameter under another name.

    `configured_env` is depended on and not used: `app.api.deps` is an application
    module and anything it imports may build a `Settings` (`docs/MISTAKES.md`
    entry 40).
    """
    try:
        module = importlib.import_module(landing_contract.deps_module)
    except ModuleNotFoundError as missing:  # pragma: no cover - a red, not a branch
        pytest.fail(
            f"`{landing_contract.deps_module}` does not import ({missing}). E1-13 puts the door "
            "pages there — the module whose docstring already describes them."
        )

    page = getattr(module, landing_contract.no_access_function, None)
    assert callable(page), (
        f"`{landing_contract.deps_module}` exposes no callable "
        f"`{landing_contract.no_access_function}`; it exposes "
        f"{sorted(n for n in vars(module) if not n.startswith('_'))}. E1-13 replaces both doors' "
        "'no role this tool has a view for' refusals with one calm page, and this is it."
    )

    required = [
        parameter.name
        for parameter in inspect.signature(page).parameters.values()
        if parameter.default is parameter.empty
        and parameter.kind not in (parameter.VAR_POSITIONAL, parameter.VAR_KEYWORD)
    ]

    assert not required, (
        f"`{landing_contract.no_access_function}` requires {required}. The page is built from "
        "constants and takes nothing, which is what makes it impossible for it to repeat a claim, "
        "a role name or anything else a caller chose — the same property `cancelled_page` has, and "
        "for the same reason."
    )


def test_the_four_pages_a_door_can_answer_with_are_four_distinguishable_things(
    landing_contract: Any,
) -> None:
    """Four events, four testids, and no two of them the same string.

    A door can answer with a landing, or with one of four pages: nothing here
    gives you a view; Pulse has no record of you; you cancelled; this tool refuses
    your token. Each is a different thing to have happened and each is owed
    different words — and each is addressed by a testid that E1-15's browser proof
    and this suite both read.

    **Dies if `no-access` is spelled as one of the other three**, which is the
    quiet way the new page arrives: reusing the refusal page's testid makes the
    calm 200 indistinguishable, in every assertion in this repository, from the
    4xx it replaces.

    This test needs no implementation — it is about the four constants this suite
    addresses the pages by — so it is green now and stays green. **A red here means
    these tests are broken rather than the doors are.**
    """
    spellings = (
        landing_contract.no_access_testid,
        landing_contract.no_account_testid,
        landing_contract.cancelled_testid,
        landing_contract.refused_testid,
    )

    assert len(set(spellings)) == len(spellings), (
        f"The four page testids are {list(spellings)} and two of them are the same string. Every "
        "assertion in this suite that says 'the person was met with page X rather than page Y' "
        "reads these, and two events sharing a testid makes that sentence unsayable."
    )
