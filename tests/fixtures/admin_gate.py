"""E9-02 — the admin gate, asked over HTTP on a route the tests mount themselves.

E9-02 adds `require_admin` and `csrf_verified_admin` to `app.api.deps` and no
route that uses them: the People editor's routes are E9-06's. Its done-when 10
says how the gate is driven anyway — "over HTTP on one stub route the tests
mount (MISTAKES entry 47), since the real routes are E9-06's". Two modules mount
one (the gate's own module and the CSRF family's), so the mounting and the
sessions live here and each module asserts (`docs/MISTAKES.md` entry 13).

**Where the gate sits on the stub.** Entry 47: on the pinned FastAPI a route
subclass's behaviour is discarded at dispatch, so a gate has to live in the
**endpoint's** own signature to be sure to run. The stub is an ordinary
`APIRoute` added to the built application with `add_api_route` (no
`include_router` rebuild), and the gate is a `Depends` parameter of its
endpoint. It is moved to the front of the route table so that no earlier
catch-all can answer for it. `test_the_stub_route_runs_the_gate_its_endpoint_
declares` is the control that this instrument works at all, with a gate that is
not E9-02's.

**The sessions are minted, not launched**, through
`tests/fixtures/lead_review.py::LeadReviewWorld.minted`'s device. An `ADMIN` or
`CARE` session is minted at the **web door**, because SPEC §2.1 makes those
web-door-only roles (`role_assignment.permits_launch` is false for `CARE`, ADR
0026). The web door is found as "the member of `Door` that is not `LAUNCH`", so
this file spells no member the suite has not already used.

**Nothing here decides an answer.** It plants rows, mints sessions, mounts a
route and makes requests. Every guard on a deliverable E9-02 owes is a plain
function called from a test body, so an unbuilt tree is a FAILED naming
`require_admin`, never an ERROR in setup (`docs/MISTAKES.md` entry 44). This
module defines no fixture, so it is imported directly rather than registered in
`pytest_plugins`.
"""

import inspect
from collections.abc import Callable
from contextlib import suppress
from typing import Any, NamedTuple
from uuid import uuid4

import pytest

from fixtures.lead_review import LeadReviewWorld
from fixtures.submit import CSRF_HEADER, csrf_token_for, session_cookie_names, session_secret
from fixtures.supervision import ROLE_SCOPE_GRAIN

# The ticket's "Owns": the module and the two dependency names.
DEPS_MODULE = "app.api.deps"
REQUIRE_ADMIN = "require_admin"
CSRF_VERIFIED_ADMIN = "csrf_verified_admin"

# The landing roles a session may name (`app.services.authz.LandingRole`), in the
# spelling `tests/unit/test_chosen_landing.py` already uses.
ADMIN_LANDING = "ADMIN"
CARE_LANDING = "CARE"
STUDENT_LANDING = "STUDENT"

# The assignment roles planted, in `tests/fixtures/supervision.py`'s spelling.
ADMIN_ASSIGNMENT = "ADMIN"
CARE_ASSIGNMENT = "CARE"
DEAN_ASSIGNMENT = "DEAN"

# ADR 0196: the 403 a verified session in another role gets carries
# `WWW-Authenticate: Bearer error="insufficient_scope"` (RFC 6750 §3.1). The
# ticket's own words: "ADR 0196's 403 marked `insufficient_scope`".
INSUFFICIENT_SCOPE = "insufficient_scope"

# What the stub's endpoint answers once the gate let a request through.
ADMITTED_BODY = {"admitted": "yes"}

GATE_IS_OWED = (
    f"E9-02 (its 'Owns'): `{DEPS_MODULE}` gains `{REQUIRE_ADMIN}` and `{CSRF_VERIFIED_ADMIN}`. "
    "A session in another role gets ADR 0196's 403 marked `insufficient_scope`; a missing or bad "
    "token gets the existing 401; an admin session is let through."
)

# "Send the double-submit token this session is entitled to" cannot be spelled
# `None`, which a test sends on purpose. The sentinel `fixtures/lead_review.py` uses.
MINTED: Any = object()


def admin_dependency(name: str) -> Any:
    """`require_admin` or `csrf_verified_admin` off `app.api.deps`, or a failure naming it."""
    import importlib

    deps = importlib.import_module(DEPS_MODULE)
    found = getattr(deps, name, None)
    if not callable(found):
        pytest.fail(f"`{DEPS_MODULE}` exposes no callable `{name}`.\n\n{GATE_IS_OWED}")
    return found


# ---------------------------------------------------------------------------
# The stub route.
# ---------------------------------------------------------------------------


def mount_stub(
    application: Any, method: str, gate: Any, on_admit: Callable[[Any], None] | None = None
) -> tuple[str, Callable[[], None]]:
    """Add one route whose endpoint declares `gate`; answer its path and a remover.

    The path carries a fresh uuid so two stubs on one application never collide,
    and the route is moved to the front of the table so nothing registered before
    it can answer its path. `on_admit` is called with whatever the gate returned,
    which is how a caller counts the writes a stub "made".
    """
    from fastapi import Depends

    path = f"/e9-02-stub/{uuid4().hex}"

    def endpoint(claims: Any = Depends(gate)) -> dict[str, str]:
        if on_admit is not None:
            on_admit(claims)
        return dict(ADMITTED_BODY)

    application.add_api_route(path, endpoint, methods=[method])
    routes = application.router.routes
    route = routes.pop()
    routes.insert(0, route)

    def remove() -> None:
        with suppress(ValueError):
            routes.remove(route)

    return path, remove


def ask(review: LeadReviewWorld, method: str, path: str, token: Any) -> Any:
    """One request carrying exactly `token` as a Bearer header and no cookie."""
    body = {} if method in {"POST", "PUT", "PATCH", "DELETE"} else None
    return review.ask(method, path, token=token, json=body)


def ask_as_a_browser(
    review: LeadReviewWorld, path: str, token: str, *, csrf_token: Any = MINTED
) -> Any:
    """One POST with the session in the cookie and no `Authorization` header.

    `fixtures/lead_review.py::LeadReviewWorld.decide_as_a_browser`'s device,
    copied (`docs/MISTAKES.md` entry 37): the jar is cleared, filled and cleared
    again on the client itself.
    """
    secret = session_secret(review.configured)
    session_cookie, csrf_cookie = session_cookie_names()
    headers: dict[str, str] = {}
    cookies = {session_cookie: token}
    if csrf_token is not None:
        value = csrf_token_for(token, secret) if csrf_token is MINTED else csrf_token
        cookies[csrf_cookie] = value
        headers[CSRF_HEADER] = value
    tool = review.tool
    tool.cookies.clear()
    try:
        for name, value in cookies.items():
            tool.cookies.set(name, value)
        return tool.post(path, json={}, headers=headers)
    finally:
        tool.cookies.clear()


# ---------------------------------------------------------------------------
# The sessions.
# ---------------------------------------------------------------------------


class Staff(NamedTuple):
    """One person, the `user` row their session names, and the session itself."""

    person_id: Any
    user_id: Any
    subject: str
    token: str


def web_door() -> Any:
    """The member of `app.services.authz.Door` that is not `LAUNCH`, or a failure."""
    from app.services.authz import Door

    others = [member for member in Door if member is not Door.LAUNCH]
    if len(others) != 1:
        pytest.fail(
            f"`Door` has {sorted(m.name for m in Door)}; SPEC §2.1 gives this system two doors, "
            "the LTI launch and the web login, so exactly one member other than `LAUNCH` was "
            "expected. A broken instrument, not a red."
        )
    return others[0]


def minted(
    review: LeadReviewWorld,
    *,
    role: str,
    person_id: Any,
    user_id: Any,
    subject: str,
    door: Any = None,
    now: int | None = None,
    secret: bytes | None = None,
) -> str:
    """`LeadReviewWorld.minted`, copied (entry 37), with the door as a parameter.

    Left at `None`, `door` is `Door.LAUNCH` exactly as the original mints every
    session; `now` and `secret` pass through untouched, as there.
    """
    import app.services.session as session_module
    from app.services.authz import Door, LandingRole

    issue = getattr(session_module, "issue_session", None)
    if not callable(issue):
        pytest.fail("`app.services.session` exposes no `issue_session`.")
    member = getattr(LandingRole, role, None)
    if member is None:
        pytest.fail(
            f"`LandingRole` has no member {role!r}; it has "
            f"{sorted(entry.name for entry in LandingRole)}."
        )
    parameters = inspect.signature(issue).parameters
    naming_a_person = [name for name in parameters if "person" in name.lower()]
    if len(naming_a_person) != 1 or "user_id" not in parameters:
        pytest.fail(
            f"`issue_session{inspect.signature(issue)}` declares {naming_a_person} naming a "
            "person and no usable `user_id`."
        )
    registration = review.door.door.driver.registration
    values: dict[str, Any] = {
        "door": Door.LAUNCH if door is None else door,
        "role": member,
        "sub": subject,
        "iss": registration.platform_row[registration.issuer_column],
        "secret": session_secret(review.configured) if secret is None else secret,
        "user_id": None if user_id is None else str(user_id),
        naming_a_person[0]: None if person_id is None else str(person_id),
    }
    if now is not None:
        if "now" not in parameters:
            pytest.fail(f"`issue_session{inspect.signature(issue)}` takes no `now`.")
        values["now"] = now
    unfilled = [
        name
        for name, parameter in parameters.items()
        if parameter.default is parameter.empty
        and name not in values
        and parameter.kind not in (parameter.VAR_POSITIONAL, parameter.VAR_KEYWORD)
    ]
    if unfilled:
        pytest.fail(f"`issue_session{inspect.signature(issue)}` leaves {unfilled} unfilled.")
    return issue(**values)


def a_person_holding(
    review: LeadReviewWorld,
    label: str,
    *,
    assignments: tuple[str, ...],
    landing: str,
    at_the_web_door: bool,
) -> Staff:
    """A new person holding `assignments` at each role's own grain, and a `landing` session.

    The assignments are read back, so a person who does not hold what this says
    is a broken world rather than a red.
    """
    subject = f"e9-02-{label}-{uuid4().hex[:8]}"
    person = review.web_identity.person()
    user_id = review.web_identity.user(platform_id=review._platform_id(), subject=subject)
    review.web_identity.link_person_to_user(person_id=person, user_id=user_id)
    for role in assignments:
        # A leadership role gets a scope node of its own, so no one-holder-per-node
        # rule this ticket does not mention can refuse the row (`SupervisionGraph.node`
        # gives the same reason). Care and Admin sit on the one institution.
        grain = ROLE_SCOPE_GRAIN[role]
        scope = None if grain == "institution" else review.graph.fresh_scope(grain)
        review.graph.assign(role, scope=scope, person=person)
    review.rows.commit()
    held = len(review.graph.assignments_of(person))
    assert held == len(assignments), (
        f"{label} holds {held} assignments after {len(assignments)} were planted "
        f"({assignments}). A broken world, not a red."
    )
    token = minted(
        review,
        role=landing,
        person_id=person,
        user_id=user_id,
        subject=subject,
        door=web_door() if at_the_web_door else None,
    )
    return Staff(person_id=person, user_id=user_id, subject=subject, token=token)


def an_admin(review: LeadReviewWorld, label: str = "admin") -> Staff:
    """A person holding a live `ADMIN` assignment, with an `ADMIN` session from the web door."""
    return a_person_holding(
        review, label, assignments=(ADMIN_ASSIGNMENT,), landing=ADMIN_LANDING, at_the_web_door=True
    )


def a_care_holder(review: LeadReviewWorld) -> Staff:
    """A person holding a live `CARE` assignment, with a `CARE` session from the web door."""
    return a_person_holding(
        review, "care", assignments=(CARE_ASSIGNMENT,), landing=CARE_LANDING, at_the_web_door=True
    )


def a_student(review: LeadReviewWorld) -> str:
    """A `STUDENT` session for a real `user` row and no person (ADR 0028)."""
    subject = f"e9-02-student-{uuid4().hex[:8]}"
    user_id = review.web_identity.user(platform_id=review._platform_id(), subject=subject)
    return minted(review, role=STUDENT_LANDING, person_id=None, user_id=user_id, subject=subject)
