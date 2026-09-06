"""Who may run a passback on demand — E3-07's `/dev/passback` trigger, and what refuses it.

Criterion 2: "The trigger is refused outside development, asserted in both
directions (present and working in development, refused elsewhere), the shape
ADR 0063 and 0064 already require." This module is the refusing half, asserted
without a network and without a database, exactly the way
`tests/unit/test_dev_clock_control_exposure.py` asserts the clock control's gate
and `tests/unit/test_dev_console_exposure.py` asserts the console's.

**Why this is a gate and not a convenience.** The trigger runs SPEC §3.4's
passback sweep against every eligible section: it computes each student's
participation percentage and posts it into a real LMS gradebook over AGS. A
stranger who can reach it on a deployment can make this tool write to every
gradebook it holds an address for, on demand and as often as they like —
unauthenticated, because the `/dev` console has no session and no CSRF token.
Outside development it must not exist at all.

**Two gates in one route, and their order is the security property.** E3-07's
work order (D4) puts the environment-and-method refusal *before* the origin
check. Outside development every method answers a bare 404, including a
cross-site POST: a 403 there would tell an unauthenticated caller that this build
carries a passback trigger and that its origin check is running, which is the
disclosure the 404 exists to prevent. Inside development the origin check
answers, and this module asserts both of its refusing directions.

**Which directions live here, and which do not.** Everything that must be
refused is here, because a refusal needs no gradebook. The two accepted
directions — a same-origin POST and a POST with no `Origin` header at all — are
in `tests/integration/test_the_dev_trigger_runs_a_passback.py`, where there is a
section, a platform and a clock for the sweep to actually do something with. That
placement is deliberate rather than convenient: a handler that accepts a request
here would run the real sweep against whatever database `DATABASE_URL` names, and
the alternative — substituting the sweep function at its binding in `dev.py` —
would pin *how* the handler imports it, which E3-07's work order does not settle
and which is not this module's to decide. **A gate that only ever refuses cannot
be told from a control that never worked** (ADR 0079's own consequences section
says so about the console next door), so the two modules are a pair and each
names the other.

**Marked `invariant`, and this paragraph is the record of the marker moving.**
It used to say the opposite, on the argument that SPEC §4.1's isolated pass is
about what a *reader* may see while this gate protects a *write*. E3-08's
boundary round (IC-H2) read it the other way and that reading governs: a
deployment on which a stranger can pull this trigger is one where anybody can
make the tool post participation percentages into every gradebook it holds an
address for, and §3.4's ledger travels in the AGS comment beside each of them —
so the write *is* a disclosure, to every instructor holding that gradebook, of
per-week completion detail for a class nobody asked about. The neighbouring clock
control carries the marker for a weaker version of the same reason. The rule the
old paragraph got right is that a marker is a claim about scope and not a
decoration; what it got wrong is the scope.

CI runs this module in the isolated pass and treats a skip, an xfail or an empty
collection as a failure (`scripts/ci/check_invariants.py`).

Every test asking for a deployment's `ENVIRONMENT` also asks for
`deployed_identity_provider` (E0-39), for the reason
`tests/unit/test_dev_console_exposure.py` gives: with a deployment's environment
set, `.env.example`'s `mock-idp` addresses are refused at startup and
`create_app()` would raise inside the setup of a test about a completely
different gate (`docs/MISTAKES.md` entry 22).

**Every gate below is asked of BOTH `DevControlRoute` paths**, added by E3-08's
security round. E3-07's own review found a route subclass's gate discarded at
dispatch — `docs/MISTAKES.md` entry 47, whose rule ends "every gate needs one test
that drives the built application over HTTP and reads the status in both
directions" — and E3-08 registers a **second** control the same way, `POST
/dev/roster-sync`. A suite that walked only the first would go on certifying the
route class while the new door swung open on exactly the regression entry 47
records. So the paths come from `DEV_CONTROL_PATHS` and every dispatch-level case
here runs once per control.

**And the inventory itself is reconciled against the router**, because a
hand-written list of what to cover is covered exactly as well as somebody's
memory. `test_this_modules_control_inventory_is_every_dev_control_route_registered`
walks the `DevControlRoute` instances `app.api.dev`'s router holds and requires
that set to equal the one `DEV_CONTROL_PATHS` resolves to, both directions — so a
third control added later cannot get zero dispatch coverage in silence. It is an
inventory check and not a gate check; the gates are the tests below it.

**The module keeps its name deliberately**, though it now covers both. Renaming it
would move it out of `DENIAL_NAME_SHAPES`'s `_trigger_exposure` and through the
`_control_exposure` shape instead, churning the sweep that exists to notice this
module losing its marker — for a filename. What a reader needs is this paragraph,
and the paths are named in the parametrisation's own ids.

**Which failure a red here is.** Every test in this module begins by resolving its
control's path constant through `DEV_CONTROL_PATHS`, a plain call in a test body
rather than a fixture, so on a tree where either trigger is unbuilt each case is a
**FAILED** naming the constant `app.api.dev` does not expose — never an ERROR in
somebody's setup (`docs/MISTAKES.md` entry 44). It is called first in every test,
including the ones that would otherwise pass on an unbuilt tree: a refusal
asserted against a path nothing registers is satisfied by the absence rather than
by the gate, and the guard is what keeps that from reading as a green.

Once the constants exist the reds become assertions: a 404 where a 303 belongs,
a 404 where a 403 belongs, or a status other than 404 from a deployment.
"""

from typing import Any

import pytest
from fixtures.dev_console import (
    CROSS_SITE_ORIGIN,
    CROSS_SITE_REFUSED,
    DEV_CONSOLE_PATH,
    DEV_CONTROL_PATHS,
    OPAQUE_ORIGIN,
    ORIGIN_HEADER,
    PROBED_METHODS,
    registered_dev_control_paths,
)
from fixtures.routing import registered_paths

pytestmark = pytest.mark.invariant

# The two `DevControlRoute` paths every dispatch-level case below is asked of,
# as the ids the runner reports under. Sorted so the report order is stable and a
# reader comparing two runs is comparing the same rows.
DEV_CONTROLS = tuple(sorted(DEV_CONTROL_PATHS))

ENVIRONMENT_VARIABLE = "ENVIRONMENT"

# The value the whole `/dev` surface is gated on, exact — not a prefix, not
# case-folded (ADR 0063, ADR 0079).
DEVELOPMENT = "development"

# Two names that are not it, both asked, for the reason the clock module gives: a
# gate that special-cased one spelling would be caught by the other rather than
# slip through. `production` is the one an operator sets and `staging` is the one
# a deployment reaches first.
DEPLOYMENT_ENVIRONMENTS = ("production", "staging")

# The method the trigger answers, and therefore the one method excluded from the
# in-development walk below.
TRIGGER_METHOD = "POST"

# The liveness route used as the control, and a path this application registers
# nowhere — chosen the way the two sibling exposure modules choose their own: a
# string no router in this tree would collide with by accident.
HEALTHZ_PATH = "/healthz"
UNREGISTERED_PATH = "/e3-07-unregistered-path-7b1d0e"


def application_in(environment: str, monkeypatch: pytest.MonkeyPatch) -> Any:
    """`create_app()` with `ENVIRONMENT` set to `environment`.

    Built inside the test rather than in a fixture, the way `test_docs_exposure.py`
    and both sibling `/dev` exposure modules build it, so a factory that raises
    fails one test loudly instead of erroring every collection.
    """
    from app.main import create_app

    monkeypatch.setenv(ENVIRONMENT_VARIABLE, environment)
    return create_app()


def client_for(application: Any) -> Any:
    """A test client on `application`, without running its lifespan.

    The lifespan is deliberately not entered: every answer this module asks about
    is decided by the route's own gates before any handler runs, and entering it
    would drag in the database and the roster seam no refusal needs.
    """
    from fastapi.testclient import TestClient

    return TestClient(application)


def serving_normally(client: Any, environment: str) -> None:
    """`/healthz` answers 200, so a 404 below is a closed gate and not an empty application.

    The control `docs/MISTAKES.md` entry 3 asks for, and the same one both
    sibling modules run first: an application answering 404 to everything — a
    `create_app()` that failed halfway, a client built on the wrong object —
    satisfies every refusal in this module without any gate existing at all.
    """
    answered = client.get(HEALTHZ_PATH)
    assert answered.status_code == 200, (
        f"`GET {HEALTHZ_PATH}` answered {answered.status_code} with `{ENVIRONMENT_VARIABLE}` set to "
        f"{environment!r}, so this application is serving nothing and every assertion below would "
        "hold against a system with no routes rather than against a closed gate."
    )


def baseline_is_404(client: Any, environment: str) -> None:
    """An unregistered path answers 404 to every probed method, so the comparison is like for like.

    Without this, "the trigger answers 404" cannot be told from an application
    that answers 404 to every unmatched method everywhere — which would make the
    assertion true for a reason unrelated to `/dev/passback`. It is walked with
    the same method list as the trigger, so the baseline covers the non-standard
    tokens too.
    """
    answered = {
        method: client.request(method, UNREGISTERED_PATH).status_code for method in PROBED_METHODS
    }
    unexpected = {method: status for method, status in answered.items() if status != 404}
    assert not unexpected, (
        f"`{UNREGISTERED_PATH}` answered {unexpected} rather than 404 with `{ENVIRONMENT_VARIABLE}` "
        f"set to {environment!r}. That path is chosen to collide with no router in this tree; if it "
        "answers something else, this application's not-found handling has changed under it and "
        "the assertions below are no longer measured against a clean baseline."
    )


# ---------------------------------------------------------------------------
# The inventory this module's parametrisation rests on, reconciled against the
# routes that actually exist.
# ---------------------------------------------------------------------------


def test_this_modules_control_inventory_is_every_dev_control_route_registered(
    configured_env: dict[str, str],
) -> None:
    """`DEV_CONTROL_PATHS` and the registered `DevControlRoute` set are the same set.

    **Why a hand-written inventory needs this.** Every gate below is parametrised
    over `DEV_CONTROL_PATHS`, a two-entry literal in
    `tests/fixtures/dev_console.py`. Nothing reconciled it against the application
    until now, so the coverage it drives was exactly as complete as somebody's
    memory: a third control appended to the router with no entry beside it gets
    **zero** dispatch-level coverage, silently, and this module goes on reporting
    a full green over two of three doors. That is `docs/MISTAKES.md` entry 35's
    shape — a guard that enumerates and is never made to find what it missed — and
    it is the gap E3-08's own security round created by making the inventory two
    entries long instead of one.

    **The mutation this kills**: a third `DevControlRoute` registered in
    `app.api.dev` without a `DEV_CONTROL_PATHS` entry. Before this test that is
    invisible everywhere — the route serves, the console links it, every existing
    test stays green, and the new control's environment gate and origin check are
    asserted by nothing.

    **Both directions, because they are different defects with different repairs.**
    A registered control missing from the inventory is untested code. A listed path
    that no `DevControlRoute` serves is a test suite probing a door that does not
    exist, whose 404s read as a closed gate — which is the failure the route
    existence control next door is about, arriving through the inventory instead.
    The message names each difference separately.

    **What this is not.** It answers "is the class on the route" and never "does
    the gate run" — entry 47's own warning about sweeps over route tables. The
    tests below are what drive the built application over HTTP and read the status
    in both directions; this one only makes sure they are driven over everything.

    **Non-vacuity comes first**: an empty derived set makes the equality true of an
    empty inventory and false of nothing, so the walk is required to have found a
    control before its answer is compared against anything.
    """
    registered = registered_dev_control_paths()
    listed = {control: DEV_CONTROL_PATHS[control]() for control in DEV_CONTROLS}

    assert registered, (
        "Walking `app.api.dev`'s router found no `DevControlRoute` at all. Either no control is "
        "registered — in which case every 404 this module asserts is the 404 of a route nobody "
        "wrote — or the walk is reading the wrong thing: `include_router` rebuilds a plain route "
        "from its endpoint, so the subclass instances live in the router's own `routes` list and "
        "nowhere else (`docs/MISTAKES.md` entry 47). Either way the comparison below would be "
        "between two sets neither of which describes this application."
    )

    unlisted = sorted(registered - set(listed.values()))
    assert not unlisted, (
        f"`app.api.dev` registers `DevControlRoute`s at {unlisted} that `DEV_CONTROL_PATHS` does "
        f"not name (it names {listed}). Every gate in this module is parametrised over that "
        "mapping, so those controls have no environment gate and no origin check asserted "
        "anywhere — a development-only write control reachable in production, or cross-site, with "
        "a full green suite over the ones somebody remembered. Add the path to "
        "`tests/fixtures/dev_console.py` beside the others and the coverage follows."
    )
    unregistered = sorted(set(listed.values()) - registered)
    assert not unregistered, (
        f"`DEV_CONTROL_PATHS` names {unregistered}, which no `DevControlRoute` in `app.api.dev` "
        f"serves (it serves {sorted(registered)}). Every refusal this module asserts against such "
        "a path is satisfied by the path not existing, so the rows for it are green over nothing — "
        "and a control that was renamed rather than removed is now untested under its new name too."
    )


# ---------------------------------------------------------------------------
# The control, before any refusal below is believed.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("control", DEV_CONTROLS)
def test_the_passback_trigger_is_a_route_this_application_carries(
    control: str,
    configured_env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The control on every 404 in this module (`docs/MISTAKES.md` entry 3).

    "`POST /dev/passback` answers 404 in production" is satisfied perfectly by a
    build that never grew a trigger at all, and that is the likeliest way this
    module could go green while proving nothing: the refusals land first, the
    feature is left half built, and five passing tests say the gate is closed on a
    door that was never hung.

    So the control is that the path exists somewhere in this application — asked
    in **development**, where it certainly must, and asked of the route table
    rather than over HTTP, so that it says nothing about which methods answer or
    what they do. What the route *serves* is
    `tests/integration/test_the_dev_trigger_runs_a_passback.py`'s subject.

    The reading is `fixtures.routing.registered_paths`, which follows
    `_IncludedRouter.original_router`: on the pinned FastAPI a walk over
    `application.routes` sees four documentation paths and nothing this project
    serves, so a control written the obvious way is red with the feature built and
    red without it (dispute E2-04-01, ruled 2026-09-01).

    `/dev` is required beside it for the same reason `/healthz` is required in the
    refusals: an application carrying no routes at all would fail the trigger
    assertion for a reason that has nothing to do with E3-07.

    **Green for both controls, and this paragraph used to say otherwise.** It read
    "dies until E3-07's route is registered, which is the state HEAD is in", which
    has not been true since that ticket shipped. Both triggers are registered now,
    so both rows are expected green — a red here is a control whose route is not
    registered at all, and the parametrisation's id names which.

    **Must not die** once both are: this is the one test in this module that has to
    be green before the others mean anything, and it is parametrised for exactly
    that reason — a refusal asserted against an unregistered path is satisfied by
    the absence, so each control needs its own existence control rather than
    borrowing the other's.
    """
    declared = DEV_CONTROL_PATHS[control]()
    application = application_in(DEVELOPMENT, monkeypatch)
    paths = registered_paths(application)

    assert DEV_CONSOLE_PATH in paths, (
        f"This application registers no `{DEV_CONSOLE_PATH}` route at all (it registers "
        f"{sorted(paths)}). ADR 0079 includes the console's router unconditionally, so its absence "
        "here means the application was not built or its routers were not registered — and the "
        "trigger assertion below would then be about nothing."
    )
    assert declared in paths, (
        f"This application registers no route at `{declared}` (it registers {sorted(paths)}). "
        f"E3-07 adds the passback trigger to the development console and E3-08 the {control!r} "
        "one beside it, both on the same `DevControlRoute`; each runs its walk and redirects back "
        f"to `{DEV_CONSOLE_PATH}`. Until this one exists, every 404 asserted against it in this "
        "module is the 404 of a route nobody wrote."
    )


# ---------------------------------------------------------------------------
# Outside development the trigger is not there, to any method.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("control", DEV_CONTROLS)
@pytest.mark.parametrize("environment", DEPLOYMENT_ENVIRONMENTS)
def test_the_passback_trigger_answers_404_to_every_method_outside_development(
    environment: str,
    control: str,
    configured_env: dict[str, str],
    deployed_identity_provider: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Criterion 2's refusing half: a method probe of a deployment learns nothing.

    **The mutation this kills**: the environment check missing from the trigger,
    or written the wrong way round. Under it a stranger POSTs to a deployment and
    makes this tool recompute and re-post a participation grade for every student
    of every section it holds a gradebook address for — with no session, no CSRF
    token and no audit, because the `/dev` console has none of those.

    **The second mutation, and it is the one a fix usually reintroduces**: a
    closed method enumeration at registration. E2-04's security round measured
    that a route naming the six standard verbs answers `TRACE` — and any token
    nobody listed — with the router's own `405 Allow: POST`, *before* the
    in-handler gate runs, disclosing both that this build ships the control and
    that the environment is not development. Adding the missing tokens is not the
    fix; the registration matches any method and the handler's gate is what
    refuses (`docs/MISTAKES.md` entry 35).

    **The near misses it must not pass on.** A `303` is the success answer this
    route gives in development, so a handler that lost its guard fails here on the
    status. A `403` means the origin check answered *before* the environment gate,
    which is D4's order inverted and tells a cross-site prober that the route is
    there. A `405` means the router refused the method. Each is a different status
    and all of them fail this assertion.

    Both deployment names, for the reason ADR 0063 gives: the comparison is an
    equality against the one safe name, so every other name — including one nobody
    thought of — must land on the closed side.
    """
    declared = DEV_CONTROL_PATHS[control]()
    client = client_for(application_in(environment, monkeypatch))
    serving_normally(client, environment)
    baseline_is_404(client, environment)

    answered = {method: client.request(method, declared) for method in PROBED_METHODS}
    disclosing = {
        method: (response.status_code, response.headers.get("allow"))
        for method, response in answered.items()
        if response.status_code != 404
    }
    assert not disclosing, (
        f"`{declared}` answered {disclosing} with `{ENVIRONMENT_VARIABLE}` set to "
        f"{environment!r}, as `(status, Allow)` per method, while an unregistered path answered 404 "
        "to every one of them in the same run.\n\n"
        "E3-07's work order (D4) settles this route at 404 to every method outside development, "
        "which is the clock controls' answer table rather than the console's measured `405` (ADR "
        "0079, ADR 0087). This control *writes*, and to somebody else's gradebook.\n\n"
        f"If the offenders are exactly the non-standard tokens, the registration is enumerating "
        "methods and the fix is a registration that matches any method, not a longer list."
    )


@pytest.mark.parametrize("control", DEV_CONTROLS)
def test_a_cross_site_post_outside_development_answers_404_rather_than_403(
    control: str,
    configured_env: dict[str, str],
    deployed_identity_provider: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The gate order, asserted where inverting it would show: 404 before 403.

    D4 puts the environment-and-method refusal first and says why: a cross-site
    probe outside development must learn nothing, and a 403 there would confirm
    both that the route exists and that its origin check is running. The test
    above walks every method with no `Origin` at all; this one sends the header a
    cross-site form would, which is the case an implementation ordering the checks
    the other way round answers differently.

    **The mutation this kills:** the origin check hoisted above the environment
    gate — a change that looks like tightening, since it refuses more requests
    sooner, and that turns an unremarkable 404 into a disclosure.

    **Its pair** is
    `test_a_cross_site_origin_is_refused_inside_development_with_a_403` below:
    the same request, the same header, one environment apart, and the two statuses
    must differ. Neither test means much alone — this one is satisfied by a build
    with no origin check whatsoever, and that one by a build with no environment
    gate.
    """
    declared = DEV_CONTROL_PATHS[control]()
    environment = DEPLOYMENT_ENVIRONMENTS[0]
    client = client_for(application_in(environment, monkeypatch))
    serving_normally(client, environment)

    answered = client.post(declared, headers={ORIGIN_HEADER: CROSS_SITE_ORIGIN})

    assert answered.status_code == 404, (
        f"`POST {declared}` with `{ORIGIN_HEADER}: {CROSS_SITE_ORIGIN}` answered "
        f"{answered.status_code} with `{ENVIRONMENT_VARIABLE}` set to {environment!r}. A "
        f"{CROSS_SITE_REFUSED} here is the origin check answering before the environment gate, "
        "which is D4's order inverted: it tells an unauthenticated cross-site caller that this "
        "deployment ships a passback trigger and that its same-origin check is running. Outside "
        "development the route is indistinguishable from a path nobody registered. Body begins "
        f"{answered.text[:300]!r}."
    )


# ---------------------------------------------------------------------------
# Inside development: only POST, and only from this origin.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("control", DEV_CONTROLS)
def test_the_passback_trigger_answers_404_to_every_method_but_post_in_development(
    control: str,
    configured_env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The first gate's other half: in development the trigger answers POST and nothing else.

    D4's first gate refuses anything that is not a POST with the same bare 404 it
    gives outside development, so a `GET /dev/passback` typed into a browser — or
    fetched by a link checker, or prefetched — cannot run a passback. That matters
    beyond tidiness: a `GET` that writes is reachable from an `<img>` tag on any
    page, which is precisely the class of attack the origin check exists for and
    the one it cannot see.

    **The mutation this kills:** the method check dropped from the wrapper, which
    leaves every verb running the sweep; and the method check answering `405`,
    which is a different answer from the one the path gives outside development
    and therefore a way to tell the two environments apart.

    **`POST` is excluded from this walk on purpose** — it is the accepted
    direction, and it is asserted in
    `tests/integration/test_the_dev_trigger_runs_a_passback.py`, where there is a
    gradebook for it to write to. Without that pair, a build that answered 404 to
    every method including `POST` would satisfy every assertion here and ship no
    feature at all.
    """
    declared = DEV_CONTROL_PATHS[control]()
    client = client_for(application_in(DEVELOPMENT, monkeypatch))
    serving_normally(client, DEVELOPMENT)
    baseline_is_404(client, DEVELOPMENT)

    walked = [method for method in PROBED_METHODS if method != TRIGGER_METHOD]
    answered = {method: client.request(method, declared) for method in walked}
    unexpected = {
        method: (response.status_code, response.headers.get("allow"))
        for method, response in answered.items()
        if response.status_code != 404
    }
    assert not unexpected, (
        f"`{declared}` answered {unexpected} in development, as `(status, Allow)` per method, for "
        f"methods other than `{TRIGGER_METHOD}`, while an unregistered path answered 404 to every "
        "one of them in the same run.\n\n"
        "D4's first gate refuses anything that is not a POST with a bare 404 — the same answer the "
        "path gives outside development, so the two cannot be told apart, and so that a "
        "state-changing `GET` is not reachable from an image tag on somebody else's page."
    )


@pytest.mark.parametrize("control", DEV_CONTROLS)
def test_a_cross_site_origin_is_refused_inside_development_with_a_403(
    control: str,
    configured_env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The origin check, on the case it exists for: a form on another site posting here.

    A developer's browser holds no session for this console and needs none — the
    trigger is unauthenticated — so nothing but the origin distinguishes a POST
    the developer meant from one a page they happened to be reading made on their
    behalf. Every current browser sends `Origin` on a cross-site POST, which is
    what makes the check worth having; the value is one no address in this tree
    could produce, so a build that compared against the wrong thing cannot pass by
    accident.

    **The mutations this kill**: the origin check missing, which answers the 303
    of a run that happened; a check that compares the `Referer` instead, which a
    cross-site form also sends and which would carry the attacker's page; and a
    check comparing only the *host* of the header, which accepts
    `https://testserver` against an `http` origin.

    **The near miss it must not pass on:** a 404. That is the answer of a build
    with no route at all, and it is what this test reports today — the status
    assertion below distinguishes "refused because cross-site" from "refused
    because absent", which
    `test_the_passback_trigger_is_a_route_this_application_carries` is the control
    for.

    **Its pair** is the accepted direction in
    `tests/integration/test_the_dev_trigger_runs_a_passback.py`: a POST carrying
    this application's own origin runs the sweep and posts a score. A build that
    refused every origin would satisfy this test and delete the feature.
    """
    declared = DEV_CONTROL_PATHS[control]()
    client = client_for(application_in(DEVELOPMENT, monkeypatch))
    serving_normally(client, DEVELOPMENT)

    answered = client.post(declared, headers={ORIGIN_HEADER: CROSS_SITE_ORIGIN})

    assert answered.status_code == CROSS_SITE_REFUSED, (
        f"`POST {declared}` carrying `{ORIGIN_HEADER}: {CROSS_SITE_ORIGIN}` answered "
        f"{answered.status_code} in development, and E3-07's work order (D2, D4) settles "
        f"{CROSS_SITE_REFUSED}. A 303 is the answer of a run that happened, which means any page a "
        "developer opens can make their stack post participation grades to a live LMS. A 404 means "
        "the route is not there at all — the control at the top of this module is where that is "
        f"diagnosed. Body begins {answered.text[:300]!r}."
    )


@pytest.mark.parametrize("control", DEV_CONTROLS)
def test_the_literal_null_origin_is_refused_inside_development(
    control: str,
    configured_env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`Origin: null` is a mismatch, not an absence — the distinction D4 draws by hand.

    A browser sends the literal string `null` from a sandboxed iframe, from a
    `data:` or `file:` document, and after some redirects: an opaque origin. It is
    not the same as no header at all, and the difference matters in exactly one
    direction — an absent `Origin` means a caller that is not a browser (curl, a
    script, a colleague's terminal), which is not a forgery vector, while `null`
    means a browser that is deliberately withholding where it came from.

    **The mutation this kills:** the check written as `if origin and origin !=
    ours`, which passes `null` through unless the string is handled separately;
    and, from the other side, a check written as `if origin in (None, "null")`
    treating both as suspicious, which refuses every non-browser caller and is
    caught by the accepted absent-`Origin` case in
    `tests/integration/test_the_dev_trigger_runs_a_passback.py`. The two tests are
    a pair and neither is safe to write alone: together they say that `null` is
    refused *and* that an absent header is not.

    **The near miss it must not pass on** is the same 404 the test above names:
    an unbuilt route refuses this for a reason that has nothing to do with the
    string.
    """
    declared = DEV_CONTROL_PATHS[control]()
    client = client_for(application_in(DEVELOPMENT, monkeypatch))
    serving_normally(client, DEVELOPMENT)

    answered = client.post(declared, headers={ORIGIN_HEADER: OPAQUE_ORIGIN})

    assert answered.status_code == CROSS_SITE_REFUSED, (
        f"`POST {declared}` carrying `{ORIGIN_HEADER}: {OPAQUE_ORIGIN}` answered "
        f"{answered.status_code} in development, and E3-07's work order (D4) settles "
        f"{CROSS_SITE_REFUSED}: the literal {OPAQUE_ORIGIN!r} is a value that does not equal this "
        "application's own origin, so it is refused like any other mismatch. A 303 means the check "
        "read the header as absent — the shape `if origin and origin != ours` produces — and a "
        "sandboxed iframe on any page is then a passback trigger. Body begins "
        f"{answered.text[:300]!r}."
    )
