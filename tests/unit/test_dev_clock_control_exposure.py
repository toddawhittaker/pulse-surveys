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


def registered_paths(application: Any) -> set[str]:
    """Every path this application has a route for."""
    return {route.path for route in application.routes if hasattr(route, "path")}


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
def test_the_dev_clock_control_answers_404_and_never_405_to_a_get_outside_development(
    path: str,
    configured_env: dict[str, str],
    deployed_identity_provider: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The method probe learns nothing: 404, the same answer an unregistered path gives.

    E2-04's work order settles this and it is the one place these routes are
    stricter than the console beside them. ADR 0079 measured `POST /dev` → `405
    Allow: GET`, because the console's router registers `GET` alone and answers a
    method mismatch before the handler's environment check runs; ADR 0087 kept that
    disclosure deliberately. The clock control does not inherit it: outside
    development these paths answer `404` to a method they do not serve, exactly as
    a path this application never registered does.

    **The mutation this kills**: registering `POST` alone on these paths and
    letting the router answer the mismatch — the shape the console has, arrived at
    by writing the new routes the way the neighbouring one is written. Under it a
    single unauthenticated `GET` tells a caller that this build ships a clock
    control and that `ENVIRONMENT` is not `development`, which is a strictly larger
    disclosure than the console's, since a control is a thing to attack and a page
    is a thing to read.

    **The near miss it must not pass on**: an application where these paths answer
    404 because nothing registered them at all. That is what
    `test_the_dev_clock_control_is_a_route_this_application_carries` above rules
    out, and this test is worth nothing without it.

    The unregistered path beside it is the baseline the claim is measured against,
    for the reason `test_dev_console_exposure.py` gives about its own: without it,
    "these answer 404" cannot be told from an application that answers 404 to every
    unmatched method everywhere, which would make the assertion true for a reason
    unrelated to `/dev/clock`.
    """
    client = client_for(application_in(DEPLOYMENT_ENVIRONMENTS[0], monkeypatch))

    baseline = client.get(UNREGISTERED_PATH)
    assert baseline.status_code == 404, (
        f"`GET {UNREGISTERED_PATH}` answered {baseline.status_code}, not 404. This path is chosen "
        "to collide with no router in this tree; if it answers something else, this application's "
        "not-found handling has changed under it and the assertion below is no longer measured "
        "against a clean baseline."
    )

    response = client.get(path)
    assert response.status_code == 404, (
        f"`GET {path}` answered {response.status_code} with `{ENVIRONMENT_VARIABLE}` set to "
        f"{DEPLOYMENT_ENVIRONMENTS[0]!r}, and an unregistered path answers 404 in the same run. A "
        "`405` here is the router refusing the method before the environment check — the shape ADR "
        "0079 measured on `/dev` and ADR 0087 kept there — and it tells an unauthenticated caller "
        "that this build carries a clock control. E2-04's work order settles these paths at 404 to "
        f"every method outside development. `Allow` header: {response.headers.get('allow')!r}."
    )
