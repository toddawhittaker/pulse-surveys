"""What `resolve_scope` returns: a purview, a capability, and a threshold — ticket E0-11.

Three of the ticket's criteria meet in one value.

**Care is a capability and never an element of a purview.** E0-11's scope: "Care
is not composable with any reporting role — encode that here, so no later ticket
can accidentally union it into a purview", and "The resolver returns Care as a
*separate* capability rather than as an element of the purview set, so that no
union operation can ever pick it up." SPEC §2 states the rule and the reason:
"**Care is deliberately not composable** with reporting roles — its sole power is
the threat queue, kept isolated so safety re-identification never rides alongside
routine oversight access."

**Care is held because of an assignment, never because of a claim.** E0-11: "an
actor holds Care because they hold a live `CARE` role assignment (E0-09), never
because of anything in an LTI or OIDC claim. The resolver reads the assignment
table; it does not read claims for this." The source-level half of that is
`tests/unit/test_care_is_not_reachable_from_a_claim.py`, which sweeps for a
module that both reads a claim and names the role; the runtime half is here.

**The n-threshold reaches the request from configuration.** E0-11's scope: "The
n-threshold guard *interface* — the parameter and the call site — with the
threshold read from `Settings`. The suppression rules that use it are E4." SPEC §4
makes the value configurable with a default of 5, and E4's rules read it off the
scope rather than fetching it themselves, which is what makes forgetting it hard.

**The person who holds both hats is the whole point**, and E0-09 built the fixture
for it: `care_and_instructor_person` in `tests/conftest.py`, named by that ticket
as reused here. The combination is legal — the separation is between
capabilities, not between people — so the assertion is not that such a person is
refused. It is that resolving them yields the teaching grant, and only the
teaching grant, with Care beside it.

Every read runs over a `pulse_app` connection, for the reason
`test_own_grant_follows_the_role_grain.py` sets out at length.
"""

import importlib
from typing import Any

import pytest

pytestmark = pytest.mark.integration

PURVIEW_LEVELS = (
    "institution_ids",
    "college_ids",
    "department_ids",
    "prefix_ids",
    "course_ids",
    "section_ids",
)

# SPEC §4: "Small-N handling (n < 5 responses in a reporting week)… Threshold
# value is configurable (default 5)." Read out of the spec, not out of
# `.env.example` or `Settings`, so that a default quietly changed in either is a
# failure here rather than a new expectation (`docs/MISTAKES.md` entry 19).
SPEC_DEFAULT_N_THRESHOLD = 5

# A value the configuration does not carry, for the override test. Any number
# that is not the default would do; this one is asserted to differ before it is
# used, because an override that happens to equal the default proves nothing.
EXPLICIT_N_THRESHOLD = 3


def written(graph: Any, action: Any, what: str) -> Any:
    """Perform a write that has to succeed, and fail naming it when it does not.

    A copy of the helper in `tests/integration/test_role_assignment_graph.py`; see
    that module's docstring for why these are copied rather than imported.
    """
    holder: dict[str, Any] = {}

    def perform() -> None:
        holder["row"] = action()

    refused = graph.refusal(perform)
    assert refused is None, (
        f"{what} was refused: {refused}. It is a control rather than the subject: nothing after "
        "it in this test can mean anything (`docs/MISTAKES.md` entry 3)."
    )
    return holder.get("row")


def levels(purview: Any) -> dict[str, Any]:
    """Every level of one purview, by name."""
    return {name: frozenset(getattr(purview, name)) for name in PURVIEW_LEVELS}


def configured_threshold() -> int:
    """`Settings.n_threshold_default`, or a failure naming the field E0-11 reads.

    Constructed here rather than passed in, because the claim under test is that
    the scope carries *the configured value* — comparing it against a number this
    file invented would assert something else entirely.
    """
    module = importlib.import_module("app.config")
    settings_class = getattr(module, "Settings", None)
    if settings_class is None:
        pytest.fail(
            "`app.config` exposes no `Settings`. E0-02 ships it and E0-11 reads the n-threshold "
            "from it: 'the threshold read from `Settings`'."
        )
    settings = settings_class()
    value = getattr(settings, "n_threshold_default", None)
    if value is None:
        pytest.fail(
            "`Settings` has no `n_threshold_default`. `.env.example` documents "
            "`N_THRESHOLD_DEFAULT` as 'responses in a reporting week below which raw comments "
            "stay hidden from instructors and students alike (§4, §4.1 invariant 3)', and E0-11's "
            "scope reads the threshold from `Settings` rather than from a constant, because §4 "
            "makes it institution configuration."
        )
    return int(value)


def test_own_grant_on_a_care_assignment_raises_rather_than_returning_a_purview(
    authz: Any, committed_rows: Any, application_session: Any
) -> None:
    """A Care assignment has no reporting purview, so there is none to hand back.

    E0-11's criterion: "A Care assignment produces no reporting purview at all,
    and attempting to union it with a reporting assignment raises rather than
    silently widening." The raise is what makes the second half true: `Purview`
    has no idea what Care is (`tests/unit/test_a_purview_holds_nodes_and_never_a_
    capability.py`), so the only way a union could widen one is if something
    handed it a Care-derived purview to union with — and this is where that value
    would have come from.

    **Returning an empty purview is the wrong answer and the tempting one.** It is
    true in a sense — Care supervises nothing — and it is indistinguishable from a
    lead with no courses, so a caller unions it, gets its own grant back, and the
    rule is enforced by nothing. §2.1 puts Care outside the graph entirely, and
    §6.2 makes its access identity and the threat queue and no reporting data at
    all; the institution scope on the row is where the queue lives, not a span of
    oversight, and returning it would be the largest widening in the product.

    **The control is a reporting assignment resolved on the same session**, so the
    raise is known to be about the Care row rather than about `own_grant` failing
    for everything — which, over a connection that may be missing a grant, is
    exactly what it would otherwise look like.
    """
    rows = committed_rows
    graph = rows.graph
    care = written(graph, lambda: graph.assign("CARE"), "A Care assignment at the institution")
    chair = written(graph, lambda: graph.assign("CHAIR"), "A chair assignment")
    rows.commit()

    key = graph.assignment_key
    control = authz.own_grant(application_session, assignment_id=chair[key])
    assert any(levels(control).values()), (
        f"The chair's own grant came back empty ({levels(control)}), so `own_grant` resolves "
        "nothing on this session and the raise below would say nothing about Care. "
        "`test_own_grant_follows_the_role_grain.py` is where that is diagnosed."
    )

    with pytest.raises(authz.CareIsNotComposableError):
        authz.own_grant(application_session, assignment_id=care[key])


def test_a_person_holding_care_and_a_teaching_assignment_resolves_to_the_teaching_grant(
    authz: Any, committed_rows: Any, application_session: Any
) -> None:
    """The two-hat person, which E0-09 calls legal and E0-11 has to keep separate.

    E0-09 built `care_and_instructor_person` for this and said why in the fixture:
    "it is capabilities that do not compose, not people". So the person is not
    refused and the scope is not empty — what the scope holds is the section their
    teaching assignment grants, and nothing the Care assignment touches.

    **The institution is the tell.** The Care assignment is scoped to the
    institution (§2's table, E0-09's criterion 7), so a resolver that unioned it
    in produces a purview holding every college in the university — for an
    adjunct. That is the largest possible widening in this product and the one
    §4.1 item 6 forbids absolutely, and it arrives with no error, no log line and
    nothing on the screen to distinguish it from a VP's own view.
    """
    rows = committed_rows
    graph = rows.graph
    hats = graph.care_and_instructor_person()
    section = graph.scope("section")
    rows.commit()

    scope = authz.resolve_scope(application_session, person_id=hats["person"])
    held = levels(scope.purview)

    assert held == {
        name: frozenset({section}) if name == "section_ids" else frozenset()
        for name in PURVIEW_LEVELS
    }, (
        f"A person holding a `CARE` assignment and a teaching assignment resolved to {held}. §2's "
        "table gives Care 'Institution (Office of Community Standards) — threat/self-harm queue "
        "and re-identification only; **no reporting access**', and §2 states the rule outright: "
        "'Care is deliberately not composable with reporting roles.' The teaching assignment "
        "grants one section; anything else here came from the Care row, and an `institution_ids` "
        "is every college in the university."
    )


def test_a_person_holding_care_and_a_teaching_assignment_still_holds_care(
    authz: Any, committed_rows: Any, application_session: Any
) -> None:
    """The other direction: separating the two must not cost the person their Care access.

    §6.2's queue is a safety mechanism — a self-harm disclosure routes to Care
    "immediately, regardless of small-N or anonymity" — so a resolver that keeps
    Care out of the purview by dropping it entirely has closed the one path in the
    product that exists for a student in danger. E0-11: "Ticket E0-10's Care
    service asks this module whether the actor holds Care; that is the only
    supported way to ask", so both call sites are asserted: the free function the
    Care service calls, and the field on the scope every other caller reads.
    """
    rows = committed_rows
    graph = rows.graph
    hats = graph.care_and_instructor_person()
    rows.commit()

    scope = authz.resolve_scope(application_session, person_id=hats["person"])

    assert authz.holds_care(application_session, person_id=hats["person"]) is True, (
        "`holds_care` says this person does not hold Care, and they hold a live `CARE` "
        "assignment. E0-11: 'an actor holds Care because they hold a live `CARE` role assignment "
        "(E0-09), never because of anything in an LTI or OIDC claim. The resolver reads the "
        "assignment table.' §6.2's queue is the one route to a name for a student who has "
        "disclosed self-harm; a resolver that answers no has closed it."
    )
    assert scope.holds_care is True, (
        "`holds_care` answered yes and the resolved scope says no. They are the same question "
        "asked at the two supported call sites, and a caller reading the scope — every entry "
        "point in SPEC §13 — would route this person away from the queue they are staffed to "
        "work."
    )


def test_a_person_with_no_care_assignment_does_not_hold_care(
    authz: Any, committed_rows: Any, application_session: Any
) -> None:
    """The control, and the assertion §4 actually rests on.

    Care is the only role that can re-identify a student (§4: "Re-identification
    is possible only through the Care queue (§6.2), only by the Care role"), so
    the expensive direction is the false yes: a chair for whom this answers true
    is a chair who can put a name to a comment about self-harm, with the audit log
    recording the access as legitimate because by then it is.

    The same person holds a reporting assignment, so a `False` here is known to be
    about the absence of a `CARE` row rather than about the person being unknown
    to the resolver.
    """
    rows = committed_rows
    graph = rows.graph
    chair_of = graph.person()
    written(
        graph,
        lambda: graph.assign("CHAIR", person=chair_of),
        "A chair assignment for a person with no Care role",
    )
    rows.commit()

    scope = authz.resolve_scope(application_session, person_id=chair_of)

    assert authz.holds_care(application_session, person_id=chair_of) is False, (
        "`holds_care` says a chair with no `CARE` assignment holds Care. §6.2 keeps identity "
        "access away from every other role — 'comment content and identity access are visible to "
        "no other role, including Admin and the VPAA. This separation is enforced in code, not "
        "just convention.'"
    )
    assert scope.holds_care is False, (
        "The resolved scope says a chair with no `CARE` assignment holds Care, while `holds_care` "
        "says otherwise. Whichever is wrong, a caller reading the scope is the one that opens the "
        "queue."
    )


def test_a_resolved_scope_takes_its_n_threshold_from_configuration(
    authz: Any, committed_rows: Any, application_session: Any
) -> None:
    """E0-11's scope: "the threshold read from `Settings`".

    SPEC §4 makes the value institution configuration — "Threshold value is
    configurable (default 5)" — and §4.1 item 3 makes what it gates an invariant:
    "Below the n-threshold, raw comments are hidden from instructors and students
    alike." E4 writes the suppression; E0-11 makes sure the number E4 reads is the
    institution's and not a literal somebody typed at the call site.

    The spec's own default is asserted alongside, because the two failures need
    different fixes: a scope carrying a number that is not the configured one is a
    resolver defect, and a configured default that is not 5 is a configuration
    defect, and a single assertion would report either as the other.
    """
    rows = committed_rows
    graph = rows.graph
    chair_of = graph.person()
    written(graph, lambda: graph.assign("CHAIR", person=chair_of), "A chair assignment")
    rows.commit()

    configured = configured_threshold()
    scope = authz.resolve_scope(application_session, person_id=chair_of)

    assert configured == SPEC_DEFAULT_N_THRESHOLD, (
        f"`Settings.n_threshold_default` is {configured} and SPEC §4's default is "
        f"{SPEC_DEFAULT_N_THRESHOLD}: 'Small-N handling (n < 5 responses in a reporting week)… "
        "Threshold value is configurable (default 5).' This is a configuration defect rather than "
        "a resolver one — `.env.example` is where the documented default lives."
    )
    assert scope.n_threshold == configured, (
        f"The resolved scope carries an n-threshold of {scope.n_threshold} and configuration says "
        f"{configured}. A hard-coded threshold is a rule that stops being the institution's the "
        "day they change it, and §4 makes it theirs to change."
    )


def test_an_explicit_n_threshold_overrides_the_configured_default(
    authz: Any, committed_rows: Any, application_session: Any
) -> None:
    """The parameter half of E0-11's "the parameter and the call site".

    The threshold has to be overridable for the callers E4 will write — a
    recomputation over a past week, a job that answers for an institution other
    than the one in this process's configuration — and an override that is quietly
    ignored is worse than no parameter at all: the caller believes it applied, and
    §4.1 item 3 is being enforced at a number nobody chose.

    The override is asserted to differ from the configured default first, since an
    override equal to it proves nothing (`docs/MISTAKES.md` entry 3).
    """
    rows = committed_rows
    graph = rows.graph
    chair_of = graph.person()
    written(graph, lambda: graph.assign("CHAIR", person=chair_of), "A chair assignment")
    rows.commit()

    configured = configured_threshold()
    assert EXPLICIT_N_THRESHOLD != configured, (
        f"This test overrides the threshold with {EXPLICIT_N_THRESHOLD}, which is what "
        "configuration already supplies, so the assertion below cannot tell an applied override "
        "from an ignored one. Change `EXPLICIT_N_THRESHOLD` at the top of this file."
    )

    scope = authz.resolve_scope(
        application_session, person_id=chair_of, n_threshold=EXPLICIT_N_THRESHOLD
    )

    assert scope.n_threshold == EXPLICIT_N_THRESHOLD, (
        f"An explicit `n_threshold={EXPLICIT_N_THRESHOLD}` resolved to a scope carrying "
        f"{scope.n_threshold}. The argument is E0-11's own interface, and a caller that passes it "
        "has no way to discover it was dropped — the suppression E4 builds on top would run at "
        "the configured number while the caller reports the one it asked for."
    )
