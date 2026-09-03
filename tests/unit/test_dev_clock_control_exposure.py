"""Who may move the clock — E2-04's `/dev/clock` control, refused outside development.

E2-04 criterion 3: "Outside development the override is inert and the `/dev`
control answers 404 — asserted, not assumed (`docs/MISTAKES.md` entry 2)." This
module is the refusal half of that sentence, asserted without a network and
without a database, exactly the way `test_dev_console_exposure.py` asserts the
console's own gate and `test_docs_exposure.py` asserts `/docs`.

**Why this is a gate and not a convenience.** The control writes a row that the
clock service applies to every scheduling and visibility read in the product:
which survey window is open (SPEC §3.1), which term a launch lands in, whether an
enrollment is live today. A stranger who can POST to it on a deployment can open
a closed window, close an open one, and move the denominator SPEC §3.4 posts back
to the LMS as a grade. Unauthenticated, with no session and no CSRF, because the
`/dev` console has neither.

**Two directions, in two modules, and each names the other.** A gate that only
ever refuses cannot be told from a control that never worked — ADR 0079's own
consequences section says so about the console. The serving direction is
`tests/integration/test_the_dev_console_sets_and_clears_the_clock.py`, which drives
the same two routes against a real database in development and asserts the row
they write and the clock it moves.

**The 404 is asked of a method these routes do not register, too.** ADR 0079
measured `POST /dev` answering `405 Allow: GET` outside development, because the
console's router registers `GET` alone and refuses a method mismatch before the
handler's environment check ever runs — one unauthenticated request telling a
caller both that this build ships the console and that `ENVIRONMENT` is not
`development`. ADR 0087 decided to keep that disclosure and
`test_dev_console_exposure.py` pins it. E2-04's work order settles the new paths
the other way: **404 to every method outside development**, so a probe learns
nothing about whether this build carries a clock control. That is a stricter gate
than its neighbour's, deliberately, and it is what the tests below assert.

**"Every method" means every method, and the security round of 2026-09-01 is why
that sentence is now enforced rather than claimed.** The first version of this
module drove one method per test — a `GET` — and read as though it had swept the
surface. The review measured what the sweep missed: the routes answer the
non-registered verbs through a *closed enumeration* of the six standard ones, so
a method token outside that list matches no route at all and Starlette answers
`405 Allow: POST` from the router, before the in-handler gate runs. `TRACE` does
it; so does any arbitrary token. Outside development that is the disclosure ADR
0087 accepted for the console arriving on a control that *writes*, and it
falsified this module's own headline. The walk below therefore drives the seven
standard verbs **and** `TRACE` **and** an arbitrary token, and requires `404`
from every one of them. This is `docs/MISTAKES.md` entry 35 in its usual shape: a
guard that enumerates the forms a thing can take misses the form nobody listed,
and the answer is to stop enumerating rather than to enumerate further.

**What is not asserted here is the mechanism.** An in-handler check (ADR 0079's
choice, and the work order's) and a registration gated on the environment (ADR
0074's) produce the same observable outside development. This module asserts the
observable; the mechanism is the pull request's to argue and the review's to
check.

Every test requesting a deployment's `ENVIRONMENT` also requests
`deployed_identity_provider` (E0-39), for the reason
`test_dev_console_exposure.py` gives on its own production rows: with a
deployment's environment set, `.env.example`'s `mock-idp` addresses are refused at
startup and `create_app()` would raise inside the setup of a test about a
completely different gate. The fixture configures a provider that is not the mock
and changes nothing else.
"""

from typing import Any

import pytest
from fixtures.routing import registered_paths

# E2-14 item 4. This module is the only thing asserting that the clock-writing
# routes answer 404 outside development, and it carried no `invariant` marker
# while both sibling exposure modules did — measured by the E2 boundary review
# (`docs/tickets/e2/boundary-review.md`). The control it writes is unauthenticated
# and moves the clock every survey window, term lookup and live-enrollment check
# reads, so a deployment that ships it open widens what a student and a stranger
# alike can reach; CI's isolated §4.1 pass is where a gate like that belongs.
#
# **At module level rather than per test**, which is where it differs from those
# siblings. `tests/unit/test_every_confidentiality_denial_module_sits_inside_the_
# invariant_pass.py` pins that currency and gives the reason: a module holding its
# marker per test reads, to every later reader, exactly like a module inside the
# pass, and the module's *next* test inherits nothing.
pytestmark = pytest.mark.invariant

ENVIRONMENT_VARIABLE = "ENVIRONMENT"

# The value the whole `/dev` surface is gated on, exact — not a prefix, not
# case-folded (ADR 0063, ADR 0079).
DEVELOPMENT = "development"

# Two names that are not it. Both are asked, because a gate that special-cased one
# spelling would be caught by the other rather than slip through: `production` is
# the one an operator sets, and `staging` is the one a deployment reaches first.
DEPLOYMENT_ENVIRONMENTS = ("production", "staging")

# The routes E2-04 adds, spelled by its work order. `/dev` itself is here as the
# neighbour whose measured `405` these two must *not* copy.
DEV_CONSOLE_PATH = "/dev"
DEV_CLOCK_SET_PATH = "/dev/clock"
DEV_CLOCK_CLEAR_PATH = "/dev/clock/clear"
DEV_CLOCK_PATHS = (DEV_CLOCK_SET_PATH, DEV_CLOCK_CLEAR_PATH)

# The form field `POST /dev/clock` takes: an HTML `datetime-local` value, read in
# the institution's timezone. Sent even on the refusal cases, so that a 404 cannot
# be a validation error about a missing field wearing the wrong number.
PRETEND_NOW_FIELD = "pretend_now"
A_PRETEND_NOW = "2031-03-14T10:30"

# The liveness route used as the control below, and a path this application
# registers nowhere — chosen the way `test_dev_console_exposure.py` chooses its
# own: a string no router in this tree would collide with by accident.
HEALTHZ_PATH = "/healthz"
UNREGISTERED_PATH = "/e2-04-unregistered-path-4c81ae"

# The seven standard HTTP methods, and the two the security round of 2026-09-01
# added. The split is the finding, so it is written as two tuples rather than one
# list somebody would read as uniform.
#
# **The standard seven are what a closed enumeration can hold.** They are what the
# route registration lists today, and every one of them answers 404 outside
# development already — which is exactly why a sweep over them alone reported a
# clean surface.
STANDARD_METHODS = ("GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS")

# **These two are outside every enumeration, and that is their whole job.**
# `TRACE` is a real method defined by RFC 9110 that nothing in this tree registers;
# `FOO` is an arbitrary token, syntactically a valid method and certain never to
# appear in anybody's list. A route set that answers the seven above by naming them
# answers these with the router's own `405`, naming the one method it does
# register. Both are sent because they fail for the same reason and a reader
# should not have to take the general case on the strength of the specific one:
# `TRACE` shows the gap is reachable with a *standardised* verb, and `FOO` shows
# no amount of widening the list closes it.
NON_STANDARD_METHODS = ("TRACE", "FOO")

# The whole walk. `httpx` — which `starlette.testclient.TestClient` is built on —
# puts the method token on the wire verbatim and validates it against no list, so
# every one of these is sent by the ordinary client and no ASGI-level driving is
# needed. If a later pin changes that, the fallback is to call the ASGI
# application directly with a scope carrying the token, and the reason to do so
# belongs in this comment rather than in a skip.
PROBED_METHODS = STANDARD_METHODS + NON_STANDARD_METHODS


def application_in(environment: str, monkeypatch: pytest.MonkeyPatch) -> Any:
    """`create_app()` with `ENVIRONMENT` set to `environment`.

    Built inside the test rather than in a fixture, the way `test_docs_exposure.py`
    and `test_dev_console_exposure.py` build it, so a factory that raises fails one
    test loudly instead of erroring every collection.
    """
    from app.main import create_app

    monkeypatch.setenv(ENVIRONMENT_VARIABLE, environment)
    return create_app()


def client_for(application: Any) -> Any:
    """A test client on `application`, without running its lifespan.

    The lifespan is deliberately not entered: what these tests ask is decided by
    the router and the handler's environment check, and entering it would drag in
    the database and the roster seam the refusal direction does not need.
    """
    from fastapi.testclient import TestClient

    return TestClient(application)


# ---------------------------------------------------------------------------
# The control, before any refusal below is believed. A red here means these
# tests are broken, not that the gate is.
# ---------------------------------------------------------------------------


def test_the_dev_clock_control_is_a_route_this_application_carries(
    configured_env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The control on every 404 below (`docs/MISTAKES.md` entry 3).

    "`POST /dev/clock` answers 404 in production" is satisfied perfectly by a build
    that never grew a clock control at all, and that is the single most likely way
    this module could go green while proving nothing: the refusals land first, the
    feature is left half built, and three passing tests say the gate is closed on a
    door that was never hung.

    So the control is that the paths exist somewhere in this application — asked in
    **development**, where they certainly must, and asked of the route table rather
    than over HTTP so that it says nothing about which methods answer or what they
    do. What the routes serve is
    `tests/integration/test_the_dev_console_sets_and_clears_the_clock.py`'s subject.

    **The reading is `fixtures.routing.registered_paths`, and the first version of
    this test could not make it.** `docs/disputes/E2-04-01.md`, ruled 2026-09-01:
    on the pinned `fastapi` 0.141.1 `include_router` appends an `_IncludedRouter`
    with no `.path`, so a walk over `application.routes` alone finds only FastAPI's
    four documentation paths — and this test was red on its `/dev` assertion both
    on HEAD and with every E2-04 route registered, which is `docs/MISTAKES.md`
    entry 24. The shared helper follows `original_router`, and its own docstring
    carries the measurement and the reason the flattening keeps the property below
    intact: a factory that skipped its `include_router` calls appends no router to
    recurse into, so a missing router is still missing from the walk.

    **Dies if E2-04's routes are not registered**, which is the state HEAD is in.
    **Must not die** once they are: this is the one test in this module that has to
    be green before the others mean anything.

    `/dev` is required beside them for the same reason `/healthz` is required in
    the refusals below: an application that carried no routes at all would fail
    this assertion on the clock paths for a reason that has nothing to do with
    E2-04.
    """
    application = application_in(DEVELOPMENT, monkeypatch)
    paths = registered_paths(application)

    assert DEV_CONSOLE_PATH in paths, (
        f"This application registers no `{DEV_CONSOLE_PATH}` route at all (it registers "
        f"{sorted(paths)}). ADR 0079 includes the console's router unconditionally, so its absence "
        "here means the application was not built or its routers were not registered — and the "
        "clock assertion below would then be about nothing."
    )
    missing = [path for path in DEV_CLOCK_PATHS if path not in paths]
    assert not missing, (
        f"This application registers no route at {missing}. E2-04 adds the clock control to the "
        f"development console: `POST {DEV_CLOCK_SET_PATH}` takes a `{PRETEND_NOW_FIELD}` field and "
        f"sets the single override row, and `POST {DEV_CLOCK_CLEAR_PATH}` deletes it. Until these "
        "exist, every 404 asserted in this module is the 404 of a route nobody wrote. Registered "
        f"paths: {sorted(paths)}."
    )


# ---------------------------------------------------------------------------
# The gate: outside development the control is not there, to any method.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("environment", DEPLOYMENT_ENVIRONMENTS)
@pytest.mark.parametrize("path", DEV_CLOCK_PATHS)
def test_posting_to_the_dev_clock_control_answers_404_outside_development(
    path: str,
    environment: str,
    configured_env: dict[str, str],
    deployed_identity_provider: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Criterion 3: the control answers 404 where `ENVIRONMENT` is not `development`.

    **The mutation this kills**: the environment check missing from either handler,
    or written the wrong way round. Under it a stranger POSTs a pretend now to a
    deployment and moves the clock every survey window, every term lookup and every
    live-enrollment check reads (SPEC §3.1, §3.4) — with no session, no CSRF token
    and no audit, because the `/dev` console has none of those.

    **The near misses it must not pass on.** A `303` is the success answer these
    routes give in development, so a handler that forgot its guard fails here on
    the status. A `200` or a `422` means the request reached the handler and the
    handler answered about the form rather than about the environment. A `405`
    means the router refused the method, which is the *console's* measured answer
    (ADR 0079, ADR 0087) and not the one E2-04's work order settles for these
    paths; it would also confirm to an unauthenticated caller that this build
    carries a clock control. Each of those is a different status and all of them
    fail this assertion.

    **Both routes and both deployment names**, because they are four separate
    handlers-and-values and a guard applied to three of them is the shape this
    repository has shipped before. `staging` is beside `production` for the reason
    ADR 0063 gives: the comparison is an equality against the one safe name, so
    every other name — including one nobody thought of — must land on the closed
    side.

    The `/healthz` line is the control `docs/MISTAKES.md` entry 3 asks for: an
    application answering 404 to everything — a `create_app()` that failed halfway,
    a client built on the wrong object — would satisfy the assertion below without
    any gate existing at all.
    """
    client = client_for(application_in(environment, monkeypatch))

    assert client.get(HEALTHZ_PATH).status_code == 200, (
        f"`GET {HEALTHZ_PATH}` did not answer 200 with `{ENVIRONMENT_VARIABLE}` set to "
        f"{environment!r}, so this application is serving nothing and the assertion below would "
        "hold against a system with no routes rather than against a closed gate."
    )

    response = client.post(path, data={PRETEND_NOW_FIELD: A_PRETEND_NOW})
    assert response.status_code == 404, (
        f"`POST {path}` answered {response.status_code} with `{ENVIRONMENT_VARIABLE}` set to "
        f"{environment!r}. E2-04's control is gated on `{ENVIRONMENT_VARIABLE} == {DEVELOPMENT!r}` "
        "like the console it sits on; outside development it must not exist, because the row it "
        "writes moves the clock that decides which survey window is open and which enrollments "
        f"are live. Body begins {response.text[:300]!r}."
    )


@pytest.mark.parametrize("path", DEV_CLOCK_PATHS)
def test_the_dev_clock_control_answers_404_to_every_method_outside_development(
    path: str,
    configured_env: dict[str, str],
    deployed_identity_provider: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A method probe learns nothing: 404 to all of them, standard or not.

    E2-04's work order settles this and it is the one place these routes are
    stricter than the console beside them. ADR 0079 measured `POST /dev` → `405
    Allow: GET`, because the console's router registers `GET` alone and answers a
    method mismatch before the handler's environment check runs; ADR 0087 kept that
    disclosure deliberately. The clock control does not inherit it: outside
    development these paths answer `404` to **every** method, exactly as a path
    this application never registered does.

    **This test is the security round of 2026-09-01, and it is written to be red.**
    The version it replaces drove a single `GET`, which the routes answer correctly
    because `GET` is one of the six verbs their registration enumerates. The review
    drove a method *outside* that enumeration and got the router's own `405 Allow:
    POST` — before the in-handler gate ran, so the environment check never had a
    say. `TRACE` reaches it, and so does any token nobody listed. That answer
    discloses, to an unauthenticated caller in one request, both that this build
    carries a clock control and that `ENVIRONMENT` is not `development` — the
    disclosure ADR 0087 accepted on a page that can be *read*, arriving on a
    control that can be *written*.

    **The mutation this kills: restoring a closed method enumeration.** Naming the
    verbs — the six standard ones the routes list today, or those plus `TRACE`, or
    any longer list — leaves the gap open at whatever is not on the list, and each
    widening looks like a fix. `docs/MISTAKES.md` entry 35 is this exact shape: a
    guard that enumerates the currencies a thing can be held in misses the one the
    caller chose. The fix is a registration that matches any method and lets the
    handler refuse, so that what answers is the environment check rather than the
    router's method matcher.

    **The near misses it must not pass on.** *One:* an application where these
    paths answer 404 because nothing registered them at all —
    `test_the_dev_clock_control_is_a_route_this_application_carries` above rules
    that out, and this test is worth nothing without it. *Two:* a fix that makes
    these paths 404 to everything in **development** too, which satisfies every
    assertion here and deletes the feature; the accepted direction lives in
    `tests/integration/test_the_dev_console_sets_and_clears_the_clock.py`, where
    `POST /dev/clock` must go on answering 303 and writing its row, and a change
    that turns this module green by closing the routes turns that module red.

    **How the non-standard tokens are sent.** `httpx`, which
    `starlette.testclient.TestClient` is built on, writes the method token to the
    wire verbatim and checks it against no list, so `TRACE` and `FOO` go out on the
    ordinary client and nothing has to drive the ASGI application by hand. The
    whole walk is made against one application rather than one per method, and
    every offending method is collected before anything is asserted, so a failure
    names all of them at once — a fix that closes `TRACE` and leaves an arbitrary
    token open should be one more red on the same line, not a second round trip.

    The unregistered path is the baseline the claim is measured against, for the
    reason `test_dev_console_exposure.py` gives about its own: without it, "these
    answer 404" cannot be told from an application that answers 404 to every
    unmatched method everywhere, which would make the assertion true for a reason
    unrelated to `/dev/clock`. It is probed with the same walk, so the baseline
    covers the non-standard tokens too.
    """
    client = client_for(application_in(DEPLOYMENT_ENVIRONMENTS[0], monkeypatch))

    assert client.get(HEALTHZ_PATH).status_code == 200, (
        f"`GET {HEALTHZ_PATH}` did not answer 200 with `{ENVIRONMENT_VARIABLE}` set to "
        f"{DEPLOYMENT_ENVIRONMENTS[0]!r}, so this application is serving nothing and every "
        "assertion below would hold against a system with no routes rather than against a closed "
        "gate."
    )

    baseline = {
        method: client.request(method, UNREGISTERED_PATH).status_code for method in PROBED_METHODS
    }
    unexpected_baseline = {method: status for method, status in baseline.items() if status != 404}
    assert not unexpected_baseline, (
        f"`{UNREGISTERED_PATH}` answered {unexpected_baseline} rather than 404. This path is chosen "
        "to collide with no router in this tree, and it is walked with the same methods as the "
        "clock paths precisely so that the comparison below is like for like. If an unregistered "
        "path answers something other than 404 to one of these tokens, this application's "
        "not-found handling has changed under it and the assertion below is no longer measured "
        "against a clean baseline."
    )

    answered = {method: client.request(method, path) for method in PROBED_METHODS}
    disclosing = {
        method: (response.status_code, response.headers.get("allow"))
        for method, response in answered.items()
        if response.status_code != 404
    }
    assert not disclosing, (
        f"`{path}` answered {disclosing} with `{ENVIRONMENT_VARIABLE}` set to "
        f"{DEPLOYMENT_ENVIRONMENTS[0]!r}, as `(status, Allow)` per method, while an unregistered "
        "path answered 404 to every one of them in the same run.\n\n"
        "A `405` is the router refusing the method before the environment check — the shape ADR "
        "0079 measured on `/dev` and ADR 0087 kept there — and on this control it tells an "
        "unauthenticated caller that the build ships a clock control and that this is not a "
        "development environment. E2-04's work order settles these paths at 404 to every method "
        "outside development.\n\n"
        f"If the offenders are exactly {list(NON_STANDARD_METHODS)}, the registration is "
        f"enumerating methods: it names {list(STANDARD_METHODS)} and a token outside that list "
        "matches no route at all. Adding the missing tokens to the list is not the fix — the next "
        "token nobody thought of reopens it (`docs/MISTAKES.md` entry 35). Match any method at "
        "registration and let the handler's environment check be what refuses."
    )
