"""E2-14 item 2 — SPEC §4.1 invariant 2, asserted directly on the predicate that enforces it.

SPEC §4.1: "A Lead Faculty assignment never grants sibling leads' courses, at any
point in the purview union." §2.1 says the same thing from the other side: "a
Lead Faculty's grant is only the courses they lead (never sibling leads' courses,
at any point in the union)".

`app.services.authz.leadership_grant_covers` is where that invariant is enforced
on the live write path. ADR 0108 settles what it does: it "unions `_own_grant_of`
over the person's assignments whose role is in `LEADERSHIP_ROLES` — the same
statement and the same grant rules `resolve_scope` uses, no new SQL — and answers
yes if the launch's **section**, its **course**, or the **prefix** above that
course is in the union". A staff launch that fails it binds nothing and records a
`context_outside_purview` defect; a launch that passes it stores the section's
roster address permanently and hands the scheduled sync — which calls with the
tool's own credentials — that class's whole membership.

**Why this module exists.** The E2 boundary review measured
`leadership_grant_covers` **answering `True` unconditionally and surviving the
entire isolated §4.1 pass** (`docs/tickets/e2/boundary-review.md`, HIGH,
confirmed). Its only behavioural cover was one integration module,
`test_a_staff_launch_binds_only_inside_the_launchers_purview.py`, which E2-14
also marks — but a launch-driving module is a long way from the predicate, and
§4.1 item 2 deserves an assertion on the thing itself. That is what is here.

**Both directions, because either one alone is passed by a constant.** `True`
unconditionally is killed by the refusal tests; `False` unconditionally is killed
by the acceptance test, and would also break §7.3's discovery — the launch that
bootstraps every later sync of a section. The two are written as a pair over one
world, differing only in *which course* is asked about.

**The world is a sibling pair, which is what the invariant is about.** Two
courses under one prefix, each with a section, each led by a different person
with their own `LEAD_FACULTY` assignment and their own `lead_faculty_mapping`
row. Nothing distinguishes them except who leads them, so a refusal here is
evidence about the lead's grant rather than about the containment tree.

**Every read runs over `application_session`**, the `pulse_app` connection
production serves requests over, with the rows committed through
`committed_rows`. The predicate reads `public.assignment_scope`, so "it answered
no" has to be true of a connection holding only what the migrations grant —
otherwise this is a test of a superuser's view of the world. That is the same
arrangement `tests/integration/test_own_grant_follows_the_role_grain.py` uses,
and its module docstring carries the argument in full.

**The call is bound by signature rather than spelled.** No ticket and no ADR
settles the parameter names of `leadership_grant_covers`; ADR 0108 settles the
three grains it answers on and nothing else. So `covers` below reads the
function's own signature, fills the grains it finds, and **fails naming the
parameter it cannot fill** rather than guessing — which is the device
`tests/fixtures/submit.py::issue_student_session` uses for the same reason. A red
from `covers` is an interface question for the ticket, not a defect in the
predicate, and it says so in its own message.
"""

import inspect
from typing import Any

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.invariant]

# The name ADR 0108 gives the predicate, in the module SPEC §13 and E0-11 both
# put the authorization chokepoint in. Reached through the `authz` fixture, which
# turns an absent module or an absent symbol into a failed assertion rather than
# a collection error.
PREDICATE = "leadership_grant_covers"

# The three grains ADR 0108 settles: "answers yes if the launch's **section**, its
# **course**, or the **prefix** above that course is in the union". Transcribed
# from that record rather than read off the function, so this module is not
# agreeing with the implementation about what the implementation should do
# (`docs/MISTAKES.md` entry 19).
GRAINS = ("section", "course", "prefix")

# How each grain and each of the two other inputs might be spelled. The first
# entry of each is the obvious one; the alternatives are here so that a rename is
# a one-line change rather than a rewrite, which is the convention
# `tests/fixtures/supervision.py` sets for candidate lists.
GRAIN_PARAMETERS = {
    "section": ("section_id", "section", "section_node_id"),
    "course": ("course_id", "course", "course_node_id"),
    "prefix": ("prefix_id", "prefix", "prefix_node_id"),
}
SESSION_PARAMETERS = ("session", "db", "db_session", "connection")
PERSON_PARAMETERS = ("person_id", "person")

# The containment rows a second course shares with the first: everything strictly
# above a course in SPEC §2.1's hierarchy, plus the term. A copy of the constant
# in `test_own_grant_follows_the_role_grain.py`; that module's docstring explains
# why these small helpers are copied between integration modules rather than
# imported.
ABOVE_A_COURSE = ("institution", "college", "department", "prefix", "term")

LEAD_FACULTY = "LEAD_FACULTY"


def written(graph: Any, action: Any, what: str) -> Any:
    """Perform a write that has to succeed, and fail naming it when it does not.

    A copy of the helper in `test_own_grant_follows_the_role_grain.py`. A control
    that was refused makes everything after it meaningless, and a refusal reported
    as a test failure three assertions later reads as a defect in the subject
    (`docs/MISTAKES.md` entry 3).
    """
    holder: dict[str, Any] = {}

    def perform() -> None:
        holder["row"] = action()

    refused = graph.refusal(perform)
    assert refused is None, (
        f"{what} was refused: {refused}. It is a control rather than the subject: nothing after it "
        "in this test can mean anything."
    )
    return holder.get("row")


def a_course_with_a_section(rows: Any) -> dict[str, Any]:
    """A whole fresh containment chain down to one section, as a chain of rows."""
    chain = rows.graph.new_branch()
    rows.seed("section", chain)
    return chain


def a_sibling_course(rows: Any, chain: dict[str, Any]) -> dict[str, Any]:
    """A second course, with its own section, under the prefix `chain` already holds.

    This is what makes two leads *siblings* in §2.1's sense: one prefix, one
    department, one college, two courses. Seeding a `section` builds the course it
    needs and stops there, so naming the levels to keep is the whole of it.
    """
    branch = {name: row for name, row in chain.items() if name in ABOVE_A_COURSE}
    rows.seed("section", branch)
    return branch


def node_id(rows: Any, chain: dict[str, Any], level: str) -> Any:
    """The primary key of the row `chain` holds at one containment level."""
    return rows.graph.key_of(level, chain[level])


def a_lead_of(rows: Any, chain: dict[str, Any], *, person: Any = None) -> Any:
    """One person holding a `LEAD_FACULTY` assignment and the mapping for one course.

    Both rows, because E0-11's own tests write both for a lead
    (`test_a_person_with_an_assistant_dean_and_a_lead_assignment_resolves_to_their_led_course`):
    SPEC §2.1 makes the Lead Faculty mapping the Pulse-owned record of which
    courses a person leads, and the assignment is what E0-09 makes a role in this
    system. Writing one and not the other would leave which of them the grant is
    read from as this module's guess.
    """
    graph = rows.graph
    holder = graph.person() if person is None else person
    course = node_id(rows, chain, "course")
    written(graph, lambda: graph.lead_mapping(person=holder, course=course), "A lead mapping")
    written(
        graph,
        lambda: graph.assign(LEAD_FACULTY, scope=course, person=holder),
        "A lead faculty assignment on the course they lead",
    )
    return holder


def grains_the_predicate_takes(function: Any) -> dict[str, str]:
    """Which of ADR 0108's three grains this function takes, by parameter name."""
    parameters = inspect.signature(function).parameters
    return {
        grain: name for grain in GRAINS for name in GRAIN_PARAMETERS[grain] if name in parameters
    }


def covers(authz: Any, session: Any, *, person: Any, **grains: Any) -> Any:
    """Ask `leadership_grant_covers` about one context, filling only what it takes.

    **Grains the caller does not name are passed as `None`**, and ADR 0108 is why
    that is a legal call rather than a liberty: the first-launch case it exists
    for is "a dean's legitimate first launch into a brand-new course", where Pulse
    holds no `course` row and no `section` row and the prefix is the only grain
    there is. A predicate that could not be asked with two of the three empty
    could not answer that launch at all.

    A required parameter this cannot fill stops the test with a message naming it.
    That is an interface question for the ticket — ADR 0108 settles the three
    grains and settles no signature — and it is deliberately not guessed at
    (`docs/MISTAKES.md` entry 30: a fixture that supplies the value under test
    makes neither the green nor the red mean anything).
    """
    function = authz.symbol(PREDICATE)
    taken = grains_the_predicate_takes(function)
    unknown = sorted(set(grains) - set(taken))
    assert not unknown, (
        f"`{PREDICATE}` takes no parameter for the {unknown} grain(s); it takes "
        f"{sorted(inspect.signature(function).parameters)}. ADR 0108: it 'answers yes if the "
        "launch's **section**, its **course**, or the **prefix** above that course is in the "
        "union', so all three are grains it is asked about. If they arrive some other way — one "
        "context object, a tuple — that is an interface question for this ticket, and "
        "`GRAIN_PARAMETERS` at the top of this module is the one place it is taught."
    )

    positional: list[Any] = []
    keywords: dict[str, Any] = {}
    for parameter in inspect.signature(function).parameters.values():
        if parameter.kind in (parameter.VAR_POSITIONAL, parameter.VAR_KEYWORD):
            continue
        if parameter.name in SESSION_PARAMETERS:
            value: Any = session
        elif parameter.name in PERSON_PARAMETERS:
            value = person
        elif parameter.name in set(taken.values()):
            grain = next(one for one, name in taken.items() if name == parameter.name)
            value = grains.get(grain)
        elif parameter.default is not parameter.empty:
            continue
        else:
            pytest.fail(
                f"`{PREDICATE}` requires a parameter `{parameter.name}` this test has nothing to "
                f"fill from; it is offering a session, a person id and {list(GRAINS)}. ADR 0108 "
                "makes it a union over the person's leadership assignments answered on those "
                "three grains, so a fourth required input is an interface question for the ticket "
                "rather than something to invent here."
            )
        if parameter.kind is parameter.POSITIONAL_ONLY:
            positional.append(value)
        else:
            keywords[parameter.name] = value
    return function(*positional, **keywords)


def course_ids_in_the_purview(authz: Any, session: Any, person: Any) -> frozenset[Any]:
    """The `course_ids` `resolve_scope` answers for one person, as a set.

    The control this module's refusals rest on, in the currency §4.1 item 2 is
    written in: "at any point in the purview union". If the person's own course is
    not in their purview, the world was not built the way this module says it was
    and every refusal below is about a person who holds nothing.
    """
    scope = authz.resolve_scope(session, person_id=person)
    return frozenset(scope.purview.course_ids)


def test_a_leads_own_course_is_covered_at_every_grain_the_predicate_takes(
    authz: Any, committed_rows: Any, application_session: Any
) -> None:
    """The accepted direction: a lead's own course, its section and all three grains together.

    ADR 0108's decision, positive half: the predicate "answers yes if the launch's
    section, its course, or the prefix above that course is in the union", and a
    lead's own grant is the course they lead and that course's sections (SPEC
    §2.1, and `test_own_grant_follows_the_role_grain.py` asserts the levels).

    **The mutation this kills:** `leadership_grant_covers` returning `False`
    unconditionally — the cheapest way to pass the refusal tests below, and the
    one that would stop §7.3's bootstrap: "the first staff launch of a section
    bootstraps every later sync of it", and a launch that binds nothing leaves the
    section never-synced with nothing saying why.

    **The prefix grain is asked separately and is expected to answer no**, and
    that is not a contradiction of ADR 0108. Prefix-or-below means the *launch's*
    prefix is one of the three things looked for in the union; a lead's union
    holds courses and sections and no prefix node, so the prefix of their own
    course is not in it. The dean is the role for whom the prefix grain answers
    yes, and `test_a_staff_launch_binds_only_inside_the_launchers_purview.py`
    asserts that end of it through a real launch. Asked here so that "every grain
    the predicate takes" is a measured statement rather than a claim about two of
    the three.
    """
    rows = committed_rows
    mine = a_course_with_a_section(rows)
    lead = a_lead_of(rows, mine)
    rows.commit()

    course = node_id(rows, mine, "course")
    section = node_id(rows, mine, "section")
    prefix = node_id(rows, mine, "prefix")

    held = course_ids_in_the_purview(authz, application_session, lead)
    assert course in held, (
        f"The lead's own course {course!r} is not in their purview's `course_ids` ({sorted(held)}), "
        "so this person leads nothing as far as the resolver is concerned and every answer below "
        "would be about an empty union (`docs/MISTAKES.md` entry 3)."
    )

    by_section = covers(authz, application_session, person=lead, section=section)
    by_course = covers(authz, application_session, person=lead, course=course)
    by_prefix = covers(authz, application_session, person=lead, prefix=prefix)
    whole = covers(
        authz, application_session, person=lead, section=section, course=course, prefix=prefix
    )

    assert by_course, (
        f"`{PREDICATE}` answered {by_course!r} for the course this person leads. ADR 0108 unions "
        "`_own_grant_of` over their leadership assignments and answers yes when the launch's "
        "course is in the union; a no here refuses the launch that discovers a section at all."
    )
    assert by_section, (
        f"`{PREDICATE}` answered {by_section!r} for a section of the course this person leads. "
        "SPEC §2.1 gives a lead's own grant the courses they lead and those courses' sections, and "
        "ADR 0108 checks the launch's section first."
    )
    assert whole, (
        f"`{PREDICATE}` answered {whole!r} when handed the section, the course and the prefix of a "
        "context this person leads — which is the shape a real staff launch asks it in."
    )
    assert not by_prefix, (
        f"`{PREDICATE}` answered {by_prefix!r} for the prefix above this lead's own course. A "
        "lead's union holds courses and sections; a prefix in it is every sibling lead's course "
        "under that prefix, which is exactly what SPEC §4.1 item 2 forbids — and it would arrive "
        "as a yes for a launch into a course this person does not lead."
    )


def test_no_grain_of_a_sibling_leads_course_is_covered(
    authz: Any, committed_rows: Any, application_session: Any
) -> None:
    """SPEC §4.1 item 2: a sibling lead's course, at every grain, answers no.

    The reported vector verbatim (E1 boundary review M9, ADR 0108's context): "a
    Lead Faculty enrolled as a Learner in a sibling lead's course can launch from
    it, and Pulse binds that section, stores its roster address permanently, and
    pulls the full membership". The predicate is what stands between that launch
    and the binding.

    **The mutation this kills:** `leadership_grant_covers` answering `True`
    unconditionally, which the E2 boundary review measured surviving the entire
    isolated §4.1 pass. It also kills the union widened to the assignment's
    containment ancestors — a grant read off the prefix or the department above
    the led course, which is the natural over-broad reading and which hands every
    sibling lead's course to every lead under one prefix.

    **All three grains are asked separately and then together**, because a
    condition written over one of them is a plausible partial fix: a check on the
    section alone still says yes to a course-grain launch, and a check on the
    prefix alone says yes to every course under it.

    **The control comes first and is in the invariant's own currency.** The
    person's purview holds their own course and does not hold the sibling's, read
    through `resolve_scope` — §4.1 item 2 is written as "at any point in the
    purview union", so a predicate that answers no while the purview already holds
    the sibling's course would be a rule enforced in one place and broken in the
    other.
    """
    rows = committed_rows
    mine = a_course_with_a_section(rows)
    theirs = a_sibling_course(rows, mine)
    lead = a_lead_of(rows, mine)
    a_lead_of(rows, theirs)
    rows.commit()

    siblings_course = node_id(rows, theirs, "course")
    siblings_section = node_id(rows, theirs, "section")
    siblings_prefix = node_id(rows, theirs, "prefix")

    held = course_ids_in_the_purview(authz, application_session, lead)
    assert node_id(rows, mine, "course") in held, (
        f"This lead's own course is not in their purview ({sorted(held)}), so the refusals below "
        "would be about a person who leads nothing."
    )
    assert siblings_course not in held, (
        f"The sibling lead's course {siblings_course!r} is already in this lead's purview "
        f"({sorted(held)}). SPEC §4.1 item 2 forbids it 'at any point in the purview union', so "
        "the predicate's answer below is not the only thing broken."
    )
    assert siblings_prefix == node_id(rows, mine, "prefix"), (
        f"The two courses sit under different prefixes ({siblings_prefix!r} and "
        f"{node_id(rows, mine, 'prefix')!r}), so they are not siblings and a refusal below could "
        "be explained by the containment tree rather than by the lead's grant."
    )

    by_section = covers(authz, application_session, person=lead, section=siblings_section)
    by_course = covers(authz, application_session, person=lead, course=siblings_course)
    by_prefix = covers(authz, application_session, person=lead, prefix=siblings_prefix)
    whole = covers(
        authz,
        application_session,
        person=lead,
        section=siblings_section,
        course=siblings_course,
        prefix=siblings_prefix,
    )

    answered = {
        "section": by_section,
        "course": by_course,
        "prefix": by_prefix,
        "all three together": whole,
    }
    covered = sorted(grain for grain, answer in answered.items() if answer)
    assert not covered, (
        f"`{PREDICATE}` answered yes for a sibling lead's course at {covered} (it answered "
        f"{answered}). SPEC §4.1 item 2: 'A Lead Faculty assignment never grants sibling leads' "
        "courses, at any point in the purview union.' A yes here binds that section on a launch, "
        "stores its roster service address permanently under ADR 0091's first-writer-wins name, "
        "and hands the scheduled sync — which calls with the tool's own credentials — the whole "
        "membership of a class this person has no records over."
    )


def test_a_second_leadership_assignment_adds_its_own_course_and_no_siblings(
    authz: Any, committed_rows: Any, application_session: Any
) -> None:
    """The union grows by exactly the second assignment, and the sibling stays out.

    ADR 0108: "Two leadership hats compose, as §2.1 says they do. The predicate
    unions every leadership assignment the person holds." So a person leading two
    courses is covered for both — and the union is the place §4.1 item 2 names,
    "at any point in the purview union", so the sibling lead's course has to stay
    out of it with two assignments exactly as it did with one.

    **The mutation this kills:** the union taken over the *wrong* set — the first
    assignment only (which would answer no for the second course), or every
    assignment the person holds regardless of role, or a widening from
    `_own_grant_of` to the scope node's containment subtree, which with two
    assignments under one prefix is the most natural way to accidentally swallow
    the sibling.

    **Three courses under one prefix**, so "the union grew" and "the union grew by
    the right thing" are two different assertions and both are made: the second
    course answers yes, the sibling still answers no. A test that only asserted
    the sibling's refusal would pass against a second assignment that granted
    nothing at all.

    **The second assignment is asserted stored**, read back out of the database
    through `assignments_of`, because a person holding one row where this test
    believes there are two would make the whole test a slower copy of the one
    above (`docs/MISTAKES.md` entry 3).
    """
    rows = committed_rows
    graph = rows.graph
    mine = a_course_with_a_section(rows)
    also_mine = a_sibling_course(rows, mine)
    theirs = a_sibling_course(rows, mine)

    lead = a_lead_of(rows, mine)
    a_lead_of(rows, also_mine, person=lead)
    a_lead_of(rows, theirs)
    rows.commit()

    assignments = graph.assignments_of(lead)
    assert len(assignments) == 2, (
        f"This person holds {len(assignments)} assignments ({assignments}) where this test wrote "
        "two leadership ones. With one, this is the previous test again and says nothing about "
        "the union."
    )

    first_course = node_id(rows, mine, "course")
    second_course = node_id(rows, also_mine, "course")
    siblings_course = node_id(rows, theirs, "course")
    assert len({first_course, second_course, siblings_course}) == 3, (
        f"The three courses are not three rows: {first_course!r}, {second_course!r}, "
        f"{siblings_course!r}."
    )

    assert covers(authz, application_session, person=lead, course=first_course), (
        f"`{PREDICATE}` answered no for the first course this person leads once a second "
        "leadership assignment was written beside it. ADR 0108 unions the assignments; a union "
        "that loses its first term is not a union."
    )
    assert covers(authz, application_session, person=lead, course=second_course), (
        f"`{PREDICATE}` answered no for the second course this person leads. ADR 0108: 'Two "
        "leadership hats compose, as §2.1 says they do' — a chair who also leads courses is "
        "covered by either — so a second assignment that adds nothing means only the first is "
        "being read."
    )
    assert not covers(authz, application_session, person=lead, course=siblings_course), (
        f"`{PREDICATE}` answered yes for a third lead's course, held by neither of this person's "
        "two assignments. SPEC §4.1 item 2 forbids a sibling lead's course 'at any point in the "
        "purview union', and a union that widens as assignments are added is the point in it that "
        "this test exists to stand on."
    )
    assert not covers(
        authz, application_session, person=lead, section=node_id(rows, theirs, "section")
    ), (
        f"`{PREDICATE}` answered yes for a section of a third lead's course. The section grain is "
        "the one a real launch is answered on first, so a union that reaches it reaches the "
        "binding."
    )
