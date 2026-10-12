"""E9-04 — the role switch, logout and the revoked-session table: names, people and requests.

Three test modules ask the same questions of the same three routes, so the
driving lives here and each module asserts (`docs/MISTAKES.md` entry 13).

**The names are the orchestrator's settled interface, transcribed once** (the
section "E9-04 settled interface (orchestrator ruling)" of the wave-1 work
order). The three paths, the bodies, the statuses, the new
`csrf_verified_session` dependency, the `revoked_session` table and its two
functions are all spelled there. A name that turns out to be wrong is one line
in this file, and a disagreement with it is a dispute rather than a rename.

**Nothing here decides what a route should answer.** This file seeds people,
mints sessions and makes requests; every expected role list, status and
equality is written in the module that asserts it (`docs/MISTAKES.md` entries 19
and 30). In particular, which assignments a person holds is passed in by the
test (`hats`), in the open, because which roles a door offers is the question.

**Sessions are minted, not launched**, through the module both doors issue
through, exactly as `tests/fixtures/named_sets.py::NamedSetWorld.minted` mints
its two-hat person's two sessions, and copied in shape from it rather than
rewritten (`docs/MISTAKES.md` entry 37). A launch lands a two-hat person on one
view (`LANDING_PRECEDENCE`); the switch is about every other view, so the
starting session is whichever one the test names. The door is a claim the
session carries, so a minted web session is a session the web door would have
issued for the same person.

**Every guard is a plain function called from a test body, never a fixture**
(`docs/MISTAKES.md` entry 44). On a tree where E9-04 is unbuilt each test fails
as a FAILED naming the missing route, function or table, not as an ERROR in
setup. `session_switch` itself builds only E1's, E1-12's and E1-13's machinery,
all of which exists on this tree.

**The cookie jar is emptied around every request**, as
`NamedSetDoor.create_as_a_browser` empties it and for its reason: a switch sets
the new session cookie on the client, and `httpx` would send it on the next
request, so a later request meant to carry only the old token would carry the
new one too (`docs/disputes/E2-09-01.md`).

**The environment** (`docs/MISTAKES.md` entry 40): the tool is built through
`tool_doors` over `configured_env`, with the development name, and the sessions
are signed with the secret out of that same mapping.
"""

import inspect
import time
from collections.abc import Callable, Iterator
from datetime import datetime, timedelta
from typing import Any, NamedTuple
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest

from fixtures.submit import CSRF_HEADER, csrf_token_for, session_cookie_names, session_secret

# ---------------------------------------------------------------------------
# The names the settled interface spells.
# ---------------------------------------------------------------------------

AUTH_MODULE = "app.api.auth"
DEPS_MODULE = "app.api.deps"
SESSION_MODULE = "app.services.session"

# The three routes, and the constants `app.api.auth` declares them under, beside
# `LOGIN_PATH`.
SESSION_LANDINGS_PATH = "/session/landings"
SESSION_SWITCH_PATH = "/session/switch"
LOGOUT_PATH = "/session/logout"
PATH_CONSTANTS = {
    "SESSION_LANDINGS_PATH": SESSION_LANDINGS_PATH,
    "SESSION_SWITCH_PATH": SESSION_SWITCH_PATH,
    "LOGOUT_PATH": LOGOUT_PATH,
}

# The new member of the `csrf_verified_*` family: any role, the double-submit
# check from `_double_submit_verified`, Bearer exempt.
CSRF_VERIFIED_SESSION = "csrf_verified_session"

# The wire members.
CURRENT_MEMBER = "current"
LANDINGS_MEMBER = "landings"
ROLE_MEMBER = "role"
SESSION_MEMBER = "session"
DETAIL_MEMBER = "detail"

# The statuses the interface fixes.
LANDINGS_OK = 200
SWITCHED = 200
SWITCH_REFUSED = 403
UNKNOWN_ROLE = 422
LOGGED_OUT = 204
SESSION_REFUSED = 401

# The table and its columns, and the two functions in `app.services.session`.
REVOKED_SESSION_TABLE = "revoked_session"
JTI_COLUMN = "jti"
EXPIRES_AT_COLUMN = "expires_at"
REVOKE_FUNCTION = "revoke_session"
PURGE_FUNCTION = "purge_revoked_sessions"

# The three statements this suite runs against that table, written out whole
# with the settled names rather than assembled, so a reader sees the SQL.
SELECT_REVOCATIONS = "SELECT jti, expires_at FROM revoked_session"
INSERT_REVOCATION = "INSERT INTO revoked_session (jti, expires_at) VALUES (:jti, :expires_at)"
DELETE_REVOCATIONS = "DELETE FROM revoked_session WHERE jti = ANY(:jtis)"

# The landing names on the wire: the `LandingRole` member name, lowercased (the
# route segment).
STUDENT = "student"
INSTRUCTOR = "instructor"
LEADERSHIP = "leadership"
CARE = "care"
ADMIN = "admin"

# The assignment roles a test hands to `person(hats=...)`, spelled as SPEC §2.1
# spells them, which is also how `tests/fixtures/supervision.py::ROLE_ALIASES`
# keys them. `DEAN` stands for the leadership hat, as it does in
# `tests/integration/test_landing_resolves_from_assignments.py`.
INSTRUCTOR_HAT = "INSTRUCTOR"
DEAN_HAT = "DEAN"
CARE_HAT = "CARE"
ADMIN_HAT = "ADMIN"

# The two doors, by `Door` member name.
LAUNCH = "LAUNCH"
WEB = "WEB"

# One gated read per route kind, each an existing GET whose gate admits exactly
# one landing role. A revoked token is asked of these, so each must be a route
# that would admit the token if it were not revoked: the probe is chosen by the
# role the token names. The admin kind waits for E9-06, which adds the admin
# routes (the ruling's first narrowing).
STUDENT_PROBE = "/student/survey"
INSTRUCTOR_PROBE = "/instructor/sections"
LEADERSHIP_PROBE = "/leadership/comparison-sets"
PROBE_FOR = {STUDENT: STUDENT_PROBE, INSTRUCTOR: INSTRUCTOR_PROBE, LEADERSHIP: LEADERSHIP_PROBE}

# E1-08's plan, decision 4: a session lives sixty minutes. An expired token is
# minted with `now` set twice that far back, so it is expired by an hour and no
# clock jitter can move it.
SESSION_LIFETIME_SECONDS = 3600
EXPIRED_BY = 2 * SESSION_LIFETIME_SECONDS

# This suite's own values. The issuers name nothing real (RFC 2606's `.invalid`).
A_PLATFORM_ISSUER = "https://e9-04-platform.invalid"
A_PROVIDER_ISSUER = "https://e9-04-provider.invalid"
COMFORTABLY_LIVE_DAYS = 30
# The zone the enrollment window's start is computed in; thirty days wide, so no
# zone could move it across today (`.env.example` configures this one).
INSTITUTION_TIMEZONE = "America/New_York"
ENVIRONMENT_VARIABLE = "ENVIRONMENT"
DEVELOPMENT = "development"

# The two carriers ADR 0089 names, and what a request does about the CSRF pair.
BEARER = "bearer"
COOKIE = "cookie"
# "Mint the double-submit token this session is entitled to", which cannot be
# spelled `None`: `None` is the request carrying no CSRF pair at all.
MINTED: Any = object()


# ---------------------------------------------------------------------------
# The deliverables, named where a test can fail on them rather than error.
# ---------------------------------------------------------------------------


def session_function(name: str) -> Any:
    """`revoke_session` or `purge_revoked_sessions`, or a failure naming it."""
    import importlib

    module = importlib.import_module(SESSION_MODULE)
    found = getattr(module, name, None)
    if not callable(found):
        pytest.fail(
            f"`{SESSION_MODULE}` exposes no callable `{name}`. E9-04's settled interface puts "
            f"`{REVOKE_FUNCTION}(db, claims)` and `{PURGE_FUNCTION}(db, now)` there."
        )
    return found


def require_revoked_session_table(session: Any) -> None:
    """The `revoked_session` table exists with its two settled columns, or a failure saying so.

    Called as the first statement of a test body that reads or plants rows, so an
    unbuilt migration is a FAILED naming the table (`docs/MISTAKES.md` entry 44).
    """
    from sqlalchemy import inspect as inspect_database

    session.rollback()
    inspector = inspect_database(session.connection())
    if not inspector.has_table(REVOKED_SESSION_TABLE):
        pytest.fail(
            f"There is no `{REVOKED_SESSION_TABLE}` table. E9-04 adds it in migration "
            f"`e9c3f5a7b403`: `{JTI_COLUMN} text primary key, {EXPIRES_AT_COLUMN} timestamptz not "
            "null, revoked_at timestamptz not null default now()`."
        )
    columns = {column["name"] for column in inspector.get_columns(REVOKED_SESSION_TABLE)}
    missing = sorted({JTI_COLUMN, EXPIRES_AT_COLUMN} - columns)
    if missing:
        pytest.fail(
            f"`{REVOKED_SESSION_TABLE}` declares {sorted(columns)} and not {missing}. The settled "
            f"interface names `{JTI_COLUMN}` and `{EXPIRES_AT_COLUMN}`."
        )
    session.rollback()


def verified(token: str, secret: bytes) -> Any:
    """The claims `verified_session` reads off `token`, or a failure saying it refused it."""
    from app.services.session import verified_session

    claims = verified_session(token, secret)
    if claims is None:
        pytest.fail(
            f"`verified_session` refused the token {token[:40]!r}…, so there are no claims to read. "
            "A token the switch answered with is a token this application must verify."
        )
    return claims


# ---------------------------------------------------------------------------
# Reading an answer.
# ---------------------------------------------------------------------------


def set_cookie_values(response: Any) -> dict[str, str]:
    """Every cookie a response sets, by name, with the raw value (possibly empty)."""
    found: dict[str, str] = {}
    for header in response.headers.get_list("set-cookie"):
        name, _, rest = header.partition("=")
        found[name.strip()] = rest.split(";", 1)[0].strip()
    return found


def set_cookie_headers(response: Any) -> dict[str, str]:
    """Every `Set-Cookie` header a response carries, whole, keyed by cookie name."""
    return {
        header.partition("=")[0].strip(): header
        for header in response.headers.get_list("set-cookie")
    }


def is_a_clearing(header: str) -> bool:
    """Whether one `Set-Cookie` header tells the browser to drop the cookie.

    `Max-Age=0`, or an expiry in 1970, with an empty value: the two shapes a
    deletion takes (Starlette's `delete_cookie` writes both).
    """
    lowered = header.lower()
    value = header.partition("=")[2].split(";", 1)[0].strip().strip('"')
    expired = "max-age=0" in lowered or "1970" in lowered
    return expired and value == ""


def refusal_shape(response: Any) -> tuple[int, str, str | None]:
    """A 401's status, body and challenge: what "the same 401" compares."""
    return (response.status_code, response.text, response.headers.get("www-authenticate"))


def nothing_was_issued(response: Any, what: str) -> None:
    """The forbidden state, all of it: no session cookie, no CSRF cookie, no token in the body.

    `docs/MISTAKES.md` entry 2: assert the forbidden state, and assert every way it
    could arise. A refusal that set the new cookie, or that carried the new token
    in its body beside a 403, is a session issued with a refusal's status on it.
    """
    session_cookie, csrf_cookie = session_cookie_names()
    handed = sorted(set(set_cookie_values(response)) & {session_cookie, csrf_cookie})
    assert not handed, f"{what} set {handed}. A refused switch issues nothing: no cookie, no token."
    try:
        body = response.json()
    except ValueError:
        body = None
    assert not (
        isinstance(body, dict) and SESSION_MEMBER in body
    ), f"{what} carries a `{SESSION_MEMBER}` member in its body: {response.text[:300]!r}."


# ---------------------------------------------------------------------------
# The world.
# ---------------------------------------------------------------------------


class Person(NamedTuple):
    """One person this world seeded, and the handles a session is minted from."""

    person_id: Any
    user_id: Any
    subject: str
    web_subject: str
    assignments: dict[str, Any]


class SessionSwitchWorld:
    """The tool, its secret, and the people and sessions a switch is asked about."""

    def __init__(
        self,
        tool: Any,
        secret: bytes,
        rows: Any,
        web_identity: Any,
        enrol: Any,
        platform_id: Any,
    ) -> None:
        self.tool = tool
        self.secret = secret
        self.rows = rows
        self.web_identity = web_identity
        self.enrol = enrol
        self.platform_id = platform_id
        self.jtis: set[str] = set()

    # -- people -------------------------------------------------------------

    def person(self, *, hats: tuple[str, ...], enrolled: bool = False) -> Person:
        """One person holding exactly `hats`, reachable from both doors.

        A `person` row, a `user` row at this world's platform linked to it (the
        launch door's path, ADR 0024), a `web_login_subject` row linked to it
        (the web door's path, E1-12), and one `role_assignment` per hat. With
        `enrolled`, a live enrollment for the `user` row too, in a section of its
        own (ADR 0028: enrollment is the whole of a student's access).
        """
        graph = self.rows.graph
        subject = f"e9-04-lms-{uuid4()}"
        web_subject = f"e9-04-idp-{uuid4()}"
        person_id = self.web_identity.person()
        user_id = self.web_identity.user(platform_id=self.platform_id, subject=subject)
        self.web_identity.link_person_to_user(person_id=person_id, user_id=user_id)
        self.web_identity.link_web_subject(
            issuer=A_PROVIDER_ISSUER, subject=web_subject, person_id=person_id
        )
        assignments: dict[str, Any] = {}
        for hat in hats:
            if hat == INSTRUCTOR_HAT:
                assignments[hat] = graph.assign(
                    hat, scope=graph.fresh_scope("section"), person=person_id
                )
            elif hat == DEAN_HAT:
                assignments[hat] = graph.assign(
                    hat, scope=graph.fresh_scope("college"), person=person_id
                )
            elif hat in (CARE_HAT, ADMIN_HAT):
                assignments[hat] = graph.assign(
                    hat, scope=graph.scope("institution"), person=person_id, reports_to=None
                )
            else:  # pragma: no cover - a test asking for a hat this world cannot seed
                pytest.fail(f"This world seeds no {hat!r} hat.")
        self.rows.commit()
        if enrolled:
            section_id = graph.fresh_scope("section")
            self.rows.commit()
            self.enrol.enrol(
                user_id=user_id,
                section_id=section_id,
                started_on=datetime.now(ZoneInfo(INSTITUTION_TIMEZONE)).date()
                - timedelta(days=COMFORTABLY_LIVE_DAYS),
                ended_on=None,
            )
        return Person(person_id, user_id, subject, web_subject, assignments)

    def revoke_assignment(self, person: Person, hat: str) -> None:
        """Delete one of `person`'s assignments and commit (ruling 7: revoking deletes)."""
        graph = self.rows.graph
        table = graph.assignments
        key = graph.assignment_key
        row = person.assignments[hat]
        self.rows.session.execute(table.delete().where(table.c[key] == row[key]))
        self.rows.commit()

    # -- sessions -----------------------------------------------------------

    def mint(self, person: Person, *, door: str, role: str, now: int | None = None) -> str:
        """One session for `person` at `door` in landing `role`, through `issue_session`.

        Bound by signature, copied in shape from `NamedSetWorld.minted`. A web
        session carries no `user_id` (E1-12: the web door leaves it unset) and the
        provider's subject; a launch session carries both ids and the LMS subject.
        `now` is `issue_session`'s own epoch-seconds parameter, used only to mint
        an expired token.
        """
        import app.services.session as session_module
        from app.services.authz import Door, LandingRole

        issue = getattr(session_module, "issue_session", None)
        if not callable(issue):
            pytest.fail("`app.services.session` exposes no `issue_session`.")
        door_member = getattr(Door, door, None)
        role_member = getattr(LandingRole, role.upper(), None)
        if door_member is None or role_member is None:
            pytest.fail(
                f"`Door.{door}` is {door_member!r} and `LandingRole.{role.upper()}` is "
                f"{role_member!r}; the doors are {[d.name for d in Door]} and the roles "
                f"{[r.name for r in LandingRole]}."
            )
        parameters = inspect.signature(issue).parameters
        naming_a_person = [name for name in parameters if "person" in name.lower()]
        if len(naming_a_person) != 1 or "user_id" not in parameters:
            pytest.fail(
                f"`issue_session{inspect.signature(issue)}` declares {naming_a_person} naming a "
                "person and no usable `user_id`; E1-12 adds both to `SessionClaims`."
            )
        at_launch = door == LAUNCH
        values: dict[str, Any] = {
            "door": door_member,
            "role": role_member,
            "sub": person.subject if at_launch else person.web_subject,
            "iss": A_PLATFORM_ISSUER if at_launch else A_PROVIDER_ISSUER,
            "secret": self.secret,
            "user_id": str(person.user_id) if at_launch else None,
            naming_a_person[0]: str(person.person_id),
        }
        if now is not None:
            values["now"] = now
        token = str(issue(**values))
        claims = session_module.verified_session(token, self.secret)
        if claims is not None:
            self.jtis.add(str(claims.jti))
        return token

    def expired(self, person: Person, *, door: str, role: str) -> str:
        """A correctly signed token for the same person and role, expired an hour ago."""
        return self.mint(person, door=door, role=role, now=int(time.time()) - EXPIRED_BY)

    def jti_of(self, token: str) -> str:
        """The `jti` a token carries, recorded so teardown removes its revocation row."""
        jti = str(verified(token, self.secret).jti)
        self.jtis.add(jti)
        return jti

    # -- requests -----------------------------------------------------------

    def send(
        self,
        method: str,
        path: str,
        *,
        token: str | None,
        carrier: str = BEARER,
        csrf: Any = MINTED,
        json: Any = None,
    ) -> Any:
        """One request carrying `token` on `carrier`, with the jar emptied either side.

        On the cookie carrier, `csrf` is `MINTED` for the token this session is
        entitled to, `None` for no CSRF pair, or a string sent as the cookie *and*
        the header — the only shape that tells verification from a comparison of
        the two halves (`docs/disputes/E2-08-06.md`, mutation M1c). On the Bearer
        carrier it is ignored: ADR 0089 exempts that carrier.
        """
        session_cookie, csrf_cookie = session_cookie_names()
        headers: dict[str, str] = {}
        cookies: dict[str, str] = {}
        if token is not None and carrier == BEARER:
            headers["authorization"] = f"Bearer {token}"
        elif token is not None:
            cookies[session_cookie] = token
            if csrf is not None:
                value = csrf_token_for(token, self.secret) if csrf is MINTED else str(csrf)
                cookies[csrf_cookie] = value
                headers[CSRF_HEADER] = value
        self.tool.cookies.clear()
        try:
            for name, value in cookies.items():
                self.tool.cookies.set(name, value)
            return self.tool.request(method, path, headers=headers, json=json)
        finally:
            self.tool.cookies.clear()

    def landings(self, token: str | None, **how: Any) -> Any:
        return self.send("GET", SESSION_LANDINGS_PATH, token=token, **how)

    def switch(self, token: str | None, role: str, **how: Any) -> Any:
        return self.send("POST", SESSION_SWITCH_PATH, token=token, json={ROLE_MEMBER: role}, **how)

    def logout(self, token: str | None, **how: Any) -> Any:
        return self.send("POST", LOGOUT_PATH, token=token, **how)

    def probe(self, role: str, token: str | None) -> Any:
        """The gated read for one route kind, asked with `token` as a Bearer header."""
        return self.send("GET", PROBE_FOR[role], token=token)

    # -- the table ----------------------------------------------------------

    def revocation_rows(self) -> dict[str, Any]:
        """Every `revoked_session` row, `jti` to `expires_at`, read after a fresh snapshot."""
        from sqlalchemy import text

        require_revoked_session_table(self.rows.session)
        found = self.rows.session.execute(text(SELECT_REVOCATIONS)).all()
        self.rows.session.rollback()
        return {str(row[0]): row[1] for row in found}

    def plant_revocation(self, jti: str, expires_at: Any) -> None:
        """One committed `revoked_session` row this test chose, removed at teardown."""
        from sqlalchemy import text

        require_revoked_session_table(self.rows.session)
        self.rows.session.execute(text(INSERT_REVOCATION), {"jti": jti, "expires_at": expires_at})
        self.rows.commit()
        self.jtis.add(jti)

    def forget_revocations(self) -> None:
        """Remove every revocation row this world planted or caused. Teardown only."""
        from sqlalchemy import inspect as inspect_database
        from sqlalchemy import text

        if not self.jtis:
            return
        self.rows.session.rollback()
        if not inspect_database(self.rows.session.connection()).has_table(REVOKED_SESSION_TABLE):
            return
        self.rows.session.execute(text(DELETE_REVOCATIONS), {"jtis": sorted(self.jtis)})
        self.rows.commit()


@pytest.fixture
def session_switch(
    tool_doors: Any,
    door_contract: Any,
    configured_env: dict[str, str],
    committed_rows: Any,
    web_identity: Any,
    enrol: Any,
    register_platform_row: Callable[..., Any],
) -> Iterator[SessionSwitchWorld]:
    """The tool and a world to switch in. See `SessionSwitchWorld` and this module's docstring.

    Builds only machinery that exists before E9-04: the application, one
    registered platform for launch-side `user` rows, and the identity fixtures.
    """
    platform = register_platform_row(
        issuer=A_PLATFORM_ISSUER,
        authorization_endpoint="https://e9-04-platform.invalid/authorize",
        jwks_url="https://e9-04-platform.invalid/jwks",
    )
    platform_id = platform[web_identity.key_of("lti_platform")]
    tool = tool_doors(
        {
            door_contract.settings["public_base_url"]: door_contract.public_base_url,
            ENVIRONMENT_VARIABLE: DEVELOPMENT,
        },
        {},
    )
    world = SessionSwitchWorld(
        tool, session_secret(configured_env), committed_rows, web_identity, enrol, platform_id
    )
    try:
        yield world
    finally:
        world.forget_revocations()
