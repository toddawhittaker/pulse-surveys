"""E7-03 — the publish, policy, owed and on-behalf doors, and the world they are read over.

Twelve test modules drive the same routes and the same two predicates, so the
driving lives here and each module asserts (`docs/MISTAKES.md` entry 13). Nothing
in this repository answers any of it yet.

**The names E7-03's work order settles, transcribed once** ("Settled decisions"):

  - decision 1: in `app.api.instructor`, behind `csrf_verified_instructor`,
    `POST`, `PUT` and `GET …/sections/{section_id}/weeks/{course_week}/response`,
    bodies `{text, ai_seeded}`; `POST` answers 201, a second publish 409; `PUT`
    answers 200, and 409 when there is no response yet or the reader is not the
    first publisher (one sentence for both);
  - decision 2: in `app.api.leadership`, `GET …/response-policy` answering
    `{prefixes: [{prefix_id, prefix_code, courses: [{course_id, course_label,
    mode, can_set, set_by_role}]}]}`, and `PUT …/response-policy/{prefix_id}`
    taking `{mode}`, 404 with one sentence and no row when the reader can set no
    course in that prefix;
  - decision 3: `app.services.response_loop.is_owed(session, *, section_id,
    course_week, now) -> bool` and `on_behalf_open(...)`, the same keywords;
  - decision 4: `GET …/responses-owed` answering `[{section_id, section_label,
    course_week, on_behalf_open}]`;
  - decision 5: `GET …/sections/{section_id}/weeks/{course_week}/on-behalf`
    answering `{section_label, course_week, streams: [{stream, summary_text,
    response_count, rating_distribution}]}`, and `POST …/on-behalf/response-draft`,
    `POST …/on-behalf/draft-check` `{draft}`, `POST …/on-behalf/response` and
    `PUT …/on-behalf/response` `{text, ai_seeded}`; every refusal ONE 404,
    byte-identical across its causes.

**What the work order leaves open, and this file therefore does not choose.** The
members of the instructor's response view (decision 1 lists what it carries, not
how each is spelled), so no test reads one. The success status of the on-behalf
writes (any 2xx). **One reading this file does take, and says so:** the `mode` a
policy `PUT` sends and a policy read answers is spelled as the stored vocabulary
E7-01 settled (`REQUIRED`, `ENCOURAGED`), because decision 2 hands the body to
02's `record_policy`, whose `mode` is that vocabulary. A route that wants another
spelling is a one-line change in `POLICY_MODE_SPELLING` below.

**The world** is E7-02's hold world (`tests/fixtures/the_hold.py`) built on E7-04's
draft door (`tests/fixtures/response_draft.py`) instead of on the plain report
door, so every on-behalf draft and check reaches a provider the test scripts and
reads back. Nothing else differs: the same three courses under one prefix, the
same named lead, sibling lead and chair, the same calendar. The on-behalf week is
**course week 1** of the taught section `F1WW` (`FULL_WEEK`), whose report opens
on 2026-10-05 at 10:00 UTC; it holds the canonical world's five commenters, its
instructor stream shown and its course stream held. Every other section needs its
windows planted by the test that reads it (`HoldWorld.windows_for`).

**The clock.** The predicates take `now`, so their boundary pairs stand on the
second itself. A route reads the development clock, which keeps moving while it is
read (ADR 0109), so a route test stands `HTTP_MARGIN` either side of an edge —
never on it — and says so.

**Every guard on a deliverable is a plain function called from a test body**
(`docs/MISTAKES.md` entry 44), and nothing here decides an answer: it plants,
calls and reads back (entries 19 and 30).
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timedelta
from importlib import import_module
from typing import Any, NamedTuple

import pytest

from fixtures.instructor_decisions import EXCLUDE, KEEP, UNDO, a_reason
from fixtures.lead_review import (
    CHAIR_ROLE,
    LEAD_FACULTY_ROLE,
    MINTED,
    LeadReviewWorld,
    Reader,
    build_lead_review_world,
)
from fixtures.moderation import CLEAR
from fixtures.report_api import FULL_WEEK, PATH_PARAMETER
from fixtures.report_comments import decided_at_column
from fixtures.report_views import INSTRUCTOR_STREAM
from fixtures.response_draft import (
    A_PLAIN_DRAFT,
    ORDINARY_SUMMARY_VERSION,
    SHOWN_SUMMARY_RESPONSES,
    DraftDoor,
    check_answer,
    draft_answer,
    stored_themes,
)
from fixtures.routing import every_route
from fixtures.staff_names import (
    INSTRUCTOR_RESPONSE,
    RESPONSE_POLICY,
    RESPONSE_SECTION_COLUMN,
    build_staff_name_world,
)
from fixtures.student_read import decoded
from fixtures.submit import CSRF_HEADER, csrf_token_for, session_cookie_names, session_secret
from fixtures.summary_job import (
    SUMMARY_GENERATED_AT_COLUMN,
    SUMMARY_MODEL_ID_COLUMN,
    SUMMARY_PROMPT_VERSION_COLUMN,
    SUMMARY_RESPONSE_COUNT_COLUMN,
    SUMMARY_SECTION_COLUMN,
    SUMMARY_STREAM_COLUMN,
    SUMMARY_TEXT_COLUMN,
    SUMMARY_THEMES_COLUMN,
    SUMMARY_WEEK_COLUMN,
    WEEKLY_SUMMARY_TABLE,
)
from fixtures.the_hold import (
    ENCOURAGED,
    REQUIRED,
    HoldWorld,
    build_hold_world,
    report_opens,
)

# ---------------------------------------------------------------------------
# The names E7-03's work order settles, spelled once.
# ---------------------------------------------------------------------------

INSTRUCTOR_API_MODULE = "app.api.instructor"
LEADERSHIP_API_MODULE = "app.api.leadership"
SERVICE_MODULE = "app.services.response_loop"

# Decision 1 and decision 5: the request bodies.
TEXT_FIELD = "text"
AI_SEEDED_FIELD = "ai_seeded"
CHECK_DRAFT_FIELD = "draft"
MODE_FIELD = "mode"

# This file's one reading (see the module docstring): the policy body's `mode`.
POLICY_MODE_SPELLING = {REQUIRED: REQUIRED, ENCOURAGED: ENCOURAGED}

# Decision 1: the instructor's three routes, by method, and the path ending each
# is found by. `{}` stands for any one path parameter.
INSTRUCTOR_RESPONSE_ENDING = "/sections/{}/weeks/{}/response"

# Decision 2: the policy read and the policy write.
POLICY_READ_ENDING = "/response-policy"
POLICY_WRITE_ENDING = "/response-policy/{}"
PREFIXES = "prefixes"
PREFIX_ID = "prefix_id"
PREFIX_CODE = "prefix_code"
COURSES = "courses"
COURSE_ID = "course_id"
COURSE_LABEL = "course_label"
MODE = "mode"
CAN_SET = "can_set"
SET_BY_ROLE = "set_by_role"
PREFIX_MEMBERS = frozenset({PREFIX_ID, PREFIX_CODE, COURSES})
COURSE_MEMBERS = frozenset({COURSE_ID, COURSE_LABEL, MODE, CAN_SET, SET_BY_ROLE})

# Decision 4: the owed read.
OWED_ENDING = "/responses-owed"
OWED_SECTION_ID = "section_id"
OWED_SECTION_LABEL = "section_label"
OWED_COURSE_WEEK = "course_week"
OWED_ON_BEHALF_OPEN = "on_behalf_open"
OWED_MEMBERS = frozenset(
    {OWED_SECTION_ID, OWED_SECTION_LABEL, OWED_COURSE_WEEK, OWED_ON_BEHALF_OPEN}
)

# Decision 5: the on-behalf read's payload, exactly.
ON_BEHALF_MEMBERS = frozenset({"section_label", "course_week", "streams"})
STREAMS = "streams"
STREAM = "stream"
SUMMARY_TEXT = "summary_text"
STREAM_MEMBERS = frozenset({STREAM, SUMMARY_TEXT, "response_count", "rating_distribution"})

# Decision 3: the two predicates.
IS_OWED = "is_owed"
ON_BEHALF_OPEN = "on_behalf_open"

# The statuses.
OK = 200
CREATED = 201
NOT_FOUND = 404
CONFLICT = 409

# The clocks (SPEC §5.3, ruling 2): from report open.
OWED_AFTER = timedelta(hours=48)
ON_BEHALF_AFTER = timedelta(hours=96)
ONE_SECOND = timedelta(seconds=1)
# How far from an edge a *route* test stands: the development clock moves
# forward while a request is in flight (ADR 0109), so a route stood one second
# before an edge can be read after it. The predicates take `now` and stand on the
# second itself.
HTTP_MARGIN = timedelta(minutes=1)
CLEAR_PAST = timedelta(hours=1)

# The on-behalf week (see the module docstring).
ON_BEHALF_WEEK = FULL_WEEK
# The week after it, for the policy-of-record pair.
NEXT_WEEK = FULL_WEEK + 1

ROUTES_ARE_OWED = (
    "E7-03's work order settles these routes: in `app.api.instructor`, `POST`/`PUT`/`GET "
    "…/sections/{section_id}/weeks/{course_week}/response` (decision 1); in `app.api.leadership`, "
    "`GET …/response-policy` and `PUT …/response-policy/{prefix_id}` (decision 2), `GET "
    "…/responses-owed` (decision 4), and `GET …/sections/{section_id}/weeks/{course_week}/on-behalf`"
    " with `POST …/on-behalf/response-draft`, `POST …/on-behalf/draft-check`, `POST "
    "…/on-behalf/response` and `PUT …/on-behalf/response` (decision 5)."
)
PREDICATES_ARE_OWED = (
    f"E7-03's work order (decision 3) puts two predicates in `{SERVICE_MODULE}`: "
    "`is_owed(session, *, section_id, course_week, now) -> bool` (required by the policy of "
    "record, no response, `now >= report_opens_at + 48h`) and `on_behalf_open(...)` (the same at "
    "+96h), pure on read."
)


# ---------------------------------------------------------------------------
# Finding the routes (in a test body, entry 44).
# ---------------------------------------------------------------------------


def _methods(route: Any) -> set[str]:
    return {str(method).upper() for method in (getattr(route, "methods", None) or set())}


def _path(route: Any) -> str:
    return str(getattr(route, "path", "")).rstrip("/")


def _shape(path: str) -> str:
    """A path with every parameter written `{}`, so an ending can be matched by shape."""
    return PATH_PARAMETER.sub("{}", path)


def find_route(application: Any, *, module: str, method: str, ending: str) -> str:
    """The one route `module` mounts for `method` whose path ends in `ending`'s shape."""
    mounted = [
        route
        for route in every_route(application)
        if getattr(getattr(route, "endpoint", None), "__module__", None) == module
    ]
    found = [r for r in mounted if method in _methods(r) and _shape(_path(r)).endswith(ending)]
    if len(found) != 1:
        pytest.fail(
            f"`{module}` mounts {len(found)} {method} routes ending `{ending}`; it mounts "
            f"{sorted(f'{sorted(_methods(r))} {_path(r)}' for r in mounted)}.\n\n{ROUTES_ARE_OWED}"
        )
    return _path(found[0])


def fill(
    template: str, *, section_id: Any = None, course_week: Any = None, prefix: Any = None
) -> str:
    """The template with each parameter filled by what its name says it holds."""

    def value(match: Any) -> str:
        name = match.group(1).lower()
        if "section" in name and section_id is not None:
            return str(section_id)
        if "week" in name and course_week is not None:
            return str(course_week)
        if "prefix" in name and prefix is not None:
            return str(prefix)
        pytest.fail(
            f"The route {template!r} declares a parameter `{match.group(1)}` this suite cannot "
            f"fill.\n\n{ROUTES_ARE_OWED}"
        )

    return PATH_PARAMETER.sub(value, template)


class OnBehalfDoor(NamedTuple):
    """One on-behalf route: its name, its method, its ending, and whether it writes."""

    name: str
    method: str
    ending: str
    writes: bool


ON_BEHALF_READ = OnBehalfDoor("read", "GET", "/sections/{}/weeks/{}/on-behalf", False)
ON_BEHALF_DRAFT = OnBehalfDoor("draft", "POST", "/weeks/{}/on-behalf/response-draft", False)
ON_BEHALF_CHECK = OnBehalfDoor("check", "POST", "/weeks/{}/on-behalf/draft-check", False)
ON_BEHALF_PUBLISH = OnBehalfDoor("publish", "POST", "/weeks/{}/on-behalf/response", True)
ON_BEHALF_EDIT = OnBehalfDoor("edit", "PUT", "/weeks/{}/on-behalf/response", True)
ON_BEHALF_DOORS = (
    ON_BEHALF_READ,
    ON_BEHALF_DRAFT,
    ON_BEHALF_CHECK,
    ON_BEHALF_PUBLISH,
    ON_BEHALF_EDIT,
)
# The four the ticket's done-when 7 and 8 name ("read, draft, check or publish").
ON_BEHALF_FOUR = (ON_BEHALF_READ, ON_BEHALF_DRAFT, ON_BEHALF_CHECK, ON_BEHALF_PUBLISH)


def response_body(text: str, *, ai_seeded: bool = False) -> dict[str, Any]:
    return {TEXT_FIELD: text, AI_SEEDED_FIELD: ai_seeded}


# ---------------------------------------------------------------------------
# The predicates (decision 3), reached from a test body.
# ---------------------------------------------------------------------------


def the_predicate(name: str) -> Any:
    try:
        module = import_module(SERVICE_MODULE)
    except ModuleNotFoundError as missing:  # pragma: no cover - a red, not a branch
        pytest.fail(f"`{SERVICE_MODULE}` does not import ({missing}).\n\n{PREDICATES_ARE_OWED}")
    found = getattr(module, name, None)
    if not callable(found):
        pytest.fail(
            f"`{SERVICE_MODULE}` exposes no callable `{name}`; it exposes "
            f"{sorted(n for n in vars(module) if not n.startswith('_'))}.\n\n{PREDICATES_ARE_OWED}"
        )
    return found


# ---------------------------------------------------------------------------
# Reading answers.
# ---------------------------------------------------------------------------


def the_list_in(body: Any, what: str) -> list[Any]:
    """Decision 4's list: a bare list, or an object whose only member is that list."""
    if isinstance(body, list):
        return body
    if isinstance(body, dict) and len(body) == 1:
        (only,) = body.values()
        if isinstance(only, list):
            return only
    pytest.fail(f"{what} answered {str(body)[:400]!r}; decision 4 settles a list of entries.")


def same_refusal(first: Any, second: Any) -> bool:
    """Two answers a client cannot tell apart: status, body bytes, and the headers that describe it."""
    described = ("content-type", "content-length")
    return (
        first.status_code == second.status_code
        and first.content == second.content
        and all(first.headers.get(h) == second.headers.get(h) for h in described)
    )


# ---------------------------------------------------------------------------
# The world.
# ---------------------------------------------------------------------------


class LoopWorld:
    """E7-02's hold world on E7-04's draft door. See the module docstring."""

    def __init__(self, hold: HoldWorld, draft: DraftDoor) -> None:
        self.hold = hold
        self.draft = draft
        self._routes: dict[tuple[str, str, str], str] = {}

    # -- keys -----------------------------------------------------------------

    @property
    def review(self) -> LeadReviewWorld:
        return self.hold.review

    @property
    def provider(self) -> Any:
        return self.draft.provider

    @property
    def application(self) -> Any:
        return self.draft.door.application

    @property
    def lead(self) -> Reader:
        assert self.review.lead is not None
        return self.review.lead

    @property
    def sibling_lead(self) -> Reader:
        assert self.review.sibling_lead is not None
        return self.review.sibling_lead

    @property
    def chair(self) -> Reader:
        assert self.review.chair is not None
        return self.review.chair

    @property
    def teacher_token(self) -> str:
        """The taught section's instructor's own launched session."""
        return self.review.instructor_token

    @property
    def teacher_id(self) -> Any:
        return self.hold.person(self.hold.names.teacher).person_id

    # -- the clock ------------------------------------------------------------

    def stand(self, offset: timedelta, *, course_week: int = ON_BEHALF_WEEK) -> datetime:
        """Stand `offset` after the week's report opens; the instant stood at."""
        moment = report_opens(course_week) + offset
        self.hold.stand_at(moment)
        return moment

    # -- planting -------------------------------------------------------------

    def a_policy_before_the_opening(
        self,
        *,
        course: Any,
        setter: Any,
        role: str,
        mode: str = REQUIRED,
        course_week: int = ON_BEHALF_WEEK,
    ) -> None:
        """One policy row dated a day before the week's report opens, by somebody who holds `role`."""
        self.hold.a_policy(
            course=course,
            setter=setter,
            role=role,
            mode=mode,
            set_at=report_opens(course_week) - timedelta(days=1),
        )

    def own_course_required(self) -> None:
        self.a_policy_before_the_opening(
            course=self.hold.own_course, setter=self.lead.person_id, role=LEAD_FACULTY_ROLE
        )

    def sibling_course_required(self) -> None:
        self.a_policy_before_the_opening(
            course=self.hold.sibling_course,
            setter=self.sibling_lead.person_id,
            role=LEAD_FACULTY_ROLE,
        )

    def unmapped_course_required(self) -> None:
        self.a_policy_before_the_opening(
            course=self.hold.unmapped_course, setter=self.chair.person_id, role=CHAIR_ROLE
        )

    def plant_summary(self, *, text: str, themes: Any, generated_at: datetime) -> None:
        """One stored instructor-stream summary for the on-behalf week of `F1WW`, `generated_at` named."""
        self.draft.world.seed(
            WEEKLY_SUMMARY_TABLE,
            {},
            **{
                SUMMARY_SECTION_COLUMN: self.hold.taught,
                SUMMARY_WEEK_COLUMN: self.hold.week_id(ON_BEHALF_WEEK),
                SUMMARY_STREAM_COLUMN: INSTRUCTOR_STREAM,
                SUMMARY_TEXT_COLUMN: text,
                SUMMARY_RESPONSE_COUNT_COLUMN: SHOWN_SUMMARY_RESPONSES,
                SUMMARY_THEMES_COLUMN: stored_themes(themes),
                SUMMARY_PROMPT_VERSION_COLUMN: ORDINARY_SUMMARY_VERSION,
                SUMMARY_MODEL_ID_COLUMN: "e7-03-a-stored-summary-model",
                SUMMARY_GENERATED_AT_COLUMN: generated_at,
            },
        )
        self.draft.door.commit()

    def a_comment(self, text: str, *, stream: str = INSTRUCTOR_STREAM, verdict: str = CLEAR) -> Any:
        """One comment in the on-behalf week of `F1WW`; its answer id."""
        return self.draft.plant(text, stream=stream, verdict=verdict)

    def decide(self, text: str, action: str) -> datetime:
        """The teacher's decision through E6-03's own route; the instant the row was stored at."""
        reason = a_reason(40) if action == EXCLUDE else None
        self.draft.decide(text, action, reason)
        rows = self.draft.decisions.rows(self.draft.planted[text])
        assert rows, f"The {action} of {text!r} left no `moderation_state` row."
        decided_at = rows[-1][decided_at_column(self.draft.world.tables)]
        assert isinstance(decided_at, datetime), f"The stored decision time is {decided_at!r}."
        return decided_at

    def exclude(self, text: str) -> datetime:
        return self.decide(text, EXCLUDE)

    def keep_then_undo(self, text: str) -> datetime:
        """Keep a flagged comment and undo the keep; the undo's stored instant."""
        self.decide(text, KEEP)
        return self.decide(text, UNDO)

    # -- asking ---------------------------------------------------------------

    def route(self, *, module: str, method: str, ending: str) -> str:
        key = (module, method, ending)
        if key not in self._routes:
            self._routes[key] = find_route(
                self.application, module=module, method=method, ending=ending
            )
        return self._routes[key]

    def ask(self, method: str, url: str, *, token: Any, json: Any = None) -> Any:
        return self.review.ask(method, url, token=token, json=json)

    def as_a_browser(self, method: str, url: str, *, token: str, json: Any, csrf_token: Any) -> Any:
        """One request with the session in the cookie and no `Authorization` header.

        `tests/fixtures/lead_review.py::LeadReviewWorld.decide_as_a_browser`,
        copied (`docs/MISTAKES.md` entry 37). `csrf_token` is `None` for no
        double-submit pair, `MINTED` for this session's own, or a string sent as
        the cookie and the header.
        """
        secret = session_secret(self.review.configured)
        session_cookie, csrf_cookie = session_cookie_names()
        headers: dict[str, str] = {}
        cookies = {session_cookie: token}
        if csrf_token is not None:
            value = csrf_token_for(token, secret) if csrf_token is MINTED else csrf_token
            cookies[csrf_cookie] = value
            headers[CSRF_HEADER] = value
        tool = self.review.tool
        tool.cookies.clear()
        try:
            for name, cookie in cookies.items():
                tool.cookies.set(name, cookie)
            return tool.request(method, url, json=json, headers=headers)
        finally:
            tool.cookies.clear()

    # -- the instructor's routes (decision 1) ---------------------------------

    def instructor_url(
        self, method: str, *, section_id: Any = None, course_week: int = ON_BEHALF_WEEK
    ) -> str:
        template = self.route(
            module=INSTRUCTOR_API_MODULE, method=method, ending=INSTRUCTOR_RESPONSE_ENDING
        )
        section = self.hold.taught if section_id is None else section_id
        return fill(template, section_id=section, course_week=course_week)

    def instructor(
        self,
        method: str,
        *,
        text: str | None = None,
        section_id: Any = None,
        course_week: int = ON_BEHALF_WEEK,
        token: Any = None,
    ) -> Any:
        url = self.instructor_url(method, section_id=section_id, course_week=course_week)
        body = None if method == "GET" else response_body(text or "")
        return self.ask(
            method, url, token=self.teacher_token if token is None else token, json=body
        )

    # -- the policy routes (decision 2) ---------------------------------------

    def policy_read(self, reader: Any) -> Any:
        url = self.route(module=LEADERSHIP_API_MODULE, method="GET", ending=POLICY_READ_ENDING)
        return self.ask("GET", url, token=_token(reader))

    def policy_url(self, prefix: Any = None) -> str:
        template = self.route(
            module=LEADERSHIP_API_MODULE, method="PUT", ending=POLICY_WRITE_ENDING
        )
        return fill(template, prefix=self.hold.prefix if prefix is None else prefix)

    def policy_set(self, reader: Any, mode: str, *, prefix: Any = None) -> Any:
        return self.ask(
            "PUT",
            self.policy_url(prefix),
            token=_token(reader),
            json={MODE_FIELD: POLICY_MODE_SPELLING.get(mode, mode)},
        )

    def policy_courses(self, reader: Any) -> dict[str, dict[str, Any]]:
        """The reader's policy read, required 200 and in decision 2's shape, by course id."""
        answered = self.policy_read(reader)
        what = f"The policy read for {getattr(reader, 'label', 'the reader')}"
        assert answered.status_code == OK, (
            f"{what} answered {answered.status_code}. Body {answered.text[:400]!r}.\n\n"
            f"{ROUTES_ARE_OWED}"
        )
        body = decoded(answered, what)
        if not isinstance(body, dict) or set(body) != {PREFIXES}:
            pytest.fail(
                f"{what} answered {str(body)[:400]!r}; decision 2 settles `{{prefixes: [...]}}`."
            )
        found: dict[str, dict[str, Any]] = {}
        for prefix in body[PREFIXES]:
            if not isinstance(prefix, dict) or set(prefix) != PREFIX_MEMBERS:
                pytest.fail(
                    f"{what} carries a prefix entry {prefix!r}; decision 2: {sorted(PREFIX_MEMBERS)}."
                )
            for course in prefix[COURSES]:
                if not isinstance(course, dict) or set(course) != COURSE_MEMBERS:
                    pytest.fail(
                        f"{what} carries a course entry {course!r}; decision 2: {sorted(COURSE_MEMBERS)}."
                    )
                found[str(course[COURSE_ID])] = course
        return found

    # -- the owed read (decision 4) -------------------------------------------

    def owed(self, reader: Any) -> Any:
        url = self.route(module=LEADERSHIP_API_MODULE, method="GET", ending=OWED_ENDING)
        return self.ask("GET", url, token=_token(reader))

    def owed_entries(self, reader: Any) -> list[dict[str, Any]]:
        answered = self.owed(reader)
        what = f"The owed read for {getattr(reader, 'label', 'the reader')}"
        assert answered.status_code == OK, (
            f"{what} answered {answered.status_code}. Body {answered.text[:400]!r}.\n\n"
            f"{ROUTES_ARE_OWED}"
        )
        entries = the_list_in(decoded(answered, what), what)
        for entry in entries:
            if not isinstance(entry, dict) or set(entry) != OWED_MEMBERS:
                pytest.fail(
                    f"{what} carries {entry!r}; decision 4 settles exactly {sorted(OWED_MEMBERS)} — "
                    "no instructor name and no time stamp."
                )
        return entries

    # -- the on-behalf routes (decision 5) ------------------------------------

    def on_behalf_url(self, door: OnBehalfDoor, *, section_id: Any, course_week: int) -> str:
        template = self.route(module=LEADERSHIP_API_MODULE, method=door.method, ending=door.ending)
        return fill(template, section_id=section_id, course_week=course_week)

    def body_for(self, door: OnBehalfDoor, text: str) -> Any:
        if door is ON_BEHALF_READ:
            return None
        if door is ON_BEHALF_DRAFT:
            return {}
        if door is ON_BEHALF_CHECK:
            return {CHECK_DRAFT_FIELD: A_PLAIN_DRAFT}
        return response_body(text)

    def script_for(self, door: OnBehalfDoor) -> None:
        """A usable model answer for the draft and the check, so a 2xx depends on the route alone."""
        if door is ON_BEHALF_DRAFT:
            self.provider.script(draft_answer(A_PLAIN_DRAFT))
        elif door is ON_BEHALF_CHECK:
            self.provider.script(check_answer([]))

    def on_behalf(
        self,
        door: OnBehalfDoor,
        reader: Any,
        *,
        section_id: Any,
        course_week: int = ON_BEHALF_WEEK,
        text: str = "E7-03 an on-behalf response",
    ) -> Any:
        self.script_for(door)
        url = self.on_behalf_url(door, section_id=section_id, course_week=course_week)
        return self.ask(door.method, url, token=_token(reader), json=self.body_for(door, text))

    # -- reading rows ---------------------------------------------------------

    def responses_of(self, section_id: Any) -> list[dict[str, Any]]:
        return self.hold.rows_of(INSTRUCTOR_RESPONSE, RESPONSE_SECTION_COLUMN, section_id)

    def response_count(self) -> int:
        return self.hold.count(INSTRUCTOR_RESPONSE)

    def policy_count(self) -> int:
        return self.hold.count(RESPONSE_POLICY)

    def model_calls(self) -> int:
        return len(self.provider.completions)

    # -- the predicates (decision 3) ------------------------------------------

    def predicate(self, name: str, *, section_id: Any, course_week: int, now: datetime) -> bool:
        function = the_predicate(name)
        session = self.hold.application_session
        try:
            answered = function(session, section_id=section_id, course_week=course_week, now=now)
        except TypeError as mismatch:
            session.rollback()
            pytest.fail(
                f"`{name}` refused decision 3's keywords: {mismatch}\n\n{PREDICATES_ARE_OWED}"
            )
        session.rollback()
        if not isinstance(answered, bool):
            pytest.fail(f"`{name}` answered {answered!r}; decision 3: `-> bool`.")
        return answered


def _token(reader: Any) -> Any:
    return reader.token if isinstance(reader, Reader) else reader


def a_reader_for(world: LoopWorld, person_id: Any, label: str) -> Reader:
    """A fresh leadership session for somebody who already holds their grants.

    `LeadReviewWorld.a_leader` with no new grants: it links a new `user` to the
    person and mints a `LEADERSHIP` session naming them.
    """
    return world.review.a_leader(label, grants=(), person_id=person_id)


def build_loop_world(
    draft: DraftDoor,
    committed_rows: Any,
    web_identity: Any,
    enrol: Any,
    application_session: Any,
    configured: Mapping[str, str],
) -> LoopWorld:
    review = build_lead_review_world(draft.decisions, committed_rows, web_identity, configured)
    names = build_staff_name_world(review, web_identity, enrol, application_session)
    return LoopWorld(build_hold_world(names), draft)


@pytest.fixture
def response_loop(
    draft_door: DraftDoor,
    committed_rows: Any,
    web_identity: Any,
    enrol: Any,
    application_session: Any,
    configured_env: dict[str, str],
) -> LoopWorld:
    """The hold world on the draft door. See the module docstring.

    Builds nothing E7-03 owes: every route and both predicates are looked up
    inside a test body (`docs/MISTAKES.md` entry 44).
    """
    return build_loop_world(
        draft_door, committed_rows, web_identity, enrol, application_session, configured_env
    )
