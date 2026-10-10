"""E6-05 — the Lead Faculty review queue, the exclusion log, and the world they are read over.

Seven test modules ask the same three routes the same questions, so the driving
lives here and each module asserts (`docs/MISTAKES.md` entry 13). Nothing in this
repository answers any of it yet:

  - **The three routes, found rather than spelled.** E6-05's work order (decision
    1) settles them in `app.api.leadership`: a `GET …/moderation/queue`, a
    `POST …/moderation/comments/{answer_id}/decisions` taking
    `{"action": "exclude" | "keep", "reason": str | null}`, and a
    `GET …/moderation/log`. The work order writes them under `/api/`, which is
    the browser's prefix; the application serves its routes without it (the
    named-set paths are `/leadership/comparison-sets`). So each route is the one
    route of its method in that module whose path ends the way the work order
    says, the device `tests/fixtures/instructor_decisions.py::decision_route`
    uses, and a count other than one is a failure naming the work order.
  - **A world with three courses under one department**, built on the canonical
    report world (`tests/fixtures/report_api.py`) through the instructor's
    decision door (`tests/fixtures/instructor_decisions.py`):
      * the **own course** — the report world's course, holding the taught
        section `F1WW` and the untaught `Q1WW`, led by `lead`;
      * a **sibling course** under the same prefix, one section of cohort `Y`,
        led by `sibling_lead` — SPEC §4.1 item 2's subject;
      * an **unmapped course** under the same prefix, one section of cohort `4`,
        with no lead at all, so it falls to `chair` (SPEC §2.1: "A course with no
        mapping falls to its department chair").
    `chair` holds `CHAIR` on the department all three courses sit in, so the
    chair's department has two mapped courses and one unmapped one — the
    one-level-out case the ticket's known traps name (entries 35 and 53).
  - **Leadership sessions, minted.** Each reader holds real assignments (and, for
    a lead, the `lead_faculty_mapping` row E0-11's own tests write beside the
    assignment) and a `LEADERSHIP` session minted through `app.services.session`,
    exactly as `tests/fixtures/named_sets.py::NamedSetWorld.minted` mints one —
    copied, not adapted (`docs/MISTAKES.md` entry 37).

**Every request rides the built application**, which connects as `pulse_app`
(`tests/fixtures/doors.py::tool_doors` sets `DATABASE_URL` to the application
role), so every read here is a read through the connection production uses
(`docs/MISTAKES.md` entry 46).

**Nothing here decides an answer.** It plants rows, mints sessions, makes requests
and reads rows back; every expectation is written out in the test that makes it
(`docs/MISTAKES.md` entries 19 and 30). Every guard on a deliverable E6-05 owes is
a plain function called from a test body, so an unbuilt tree is a FAILED naming the
route or the copy module, never an ERROR in setup (`docs/MISTAKES.md` entry 44).
The world itself is built from machinery that already exists and names nothing
E6-05 owes.
"""

from collections.abc import Mapping
from datetime import datetime
from importlib import import_module
from typing import Any, NamedTuple
from uuid import uuid4

import pytest

from fixtures.instructor_decisions import (
    ACTION_FIELD,
    ANSWER_COLUMN,
    DECIDED_AS_COLUMN,
    DECIDER_COLUMN,
    REASON_COLUMN,
    STATE_COLUMN,
    DecisionDoor,
    require_decision_columns,
)
from fixtures.named_sets import LEADERSHIP_LANDING_ROLE
from fixtures.report_api import INSTRUCTOR_ROLE, PATH_PARAMETER
from fixtures.report_comments import decided_at_column
from fixtures.routing import every_route
from fixtures.student_read import AUTHENTICATE_SCHEME, COURSE_TABLE, PREFIX_TABLE
from fixtures.submit import (
    COPY_MAPPING_NAME,
    COPY_MODULES_FUNCTION,
    COPY_PACKAGE,
    CSRF_HEADER,
    csrf_token_for,
    issue_student_session,
    served_text,
    session_cookie_names,
    session_secret,
)
from fixtures.supervision import require_table, single_primary_key
from fixtures.survey_windows import SECTION_CODE_COLUMN, SECTION_TABLE

# ---------------------------------------------------------------------------
# The names E6-05's ticket and work order settle, spelled once.
# ---------------------------------------------------------------------------

# Work order decision 1: the module and the three routes' path endings.
LEADERSHIP_API_MODULE = "app.api.leadership"
QUEUE_ENDING = "/moderation/queue"
LOG_ENDING = "/moderation/log"
DECISION_SEGMENT = "/moderation/comments/"
DECISION_ENDING = "/decisions"

# Work order decision 1: the queue item, exactly. "No week, time, date or count."
ITEM_ANSWER_ID = "answer_id"
ITEM_TEXT = "text"
ITEM_SECTION_LABEL = "section_label"
QUEUE_ITEM_FIELDS = frozenset({ITEM_ANSWER_ID, ITEM_TEXT, ITEM_SECTION_LABEL})

# Work order decision 1: the log row, exactly, with the seventh member the ruling
# on dispute E6-05-03 adds: `decision`, the stored state token (`EXCLUDED` or
# `KEPT`), so each row says which direction it is (SPEC §5.2's "Kept / Excluded").
LOG_SECTION_LABEL = "section_label"
LOG_DECIDED_AS = "decided_as"
LOG_FLAGGED = "flagged"
LOG_REASON = "reason"
LOG_DECIDED_ON = "decided_on"
LOG_EXCERPT = "excerpt"
LOG_DECISION = "decision"
LOG_ROW_FIELDS = frozenset(
    {
        LOG_SECTION_LABEL,
        LOG_DECIDED_AS,
        LOG_FLAGGED,
        LOG_REASON,
        LOG_DECIDED_ON,
        LOG_EXCERPT,
        LOG_DECISION,
    }
)

# Work order decision 1: "Excerpt = first 140 characters".
EXCERPT_LENGTH = 140

# The two actions a lead has. There is no undo for a lead (decision 1).
EXCLUDE = "exclude"
KEEP = "keep"
UNDO = "undo"

# Work order decision 1: "a comment not in this reader's queue → 404 with one sentence".
NOT_IN_QUEUE = 404

# The ticket's "Owns": the new copy module the route's sentences live in.
LEAD_COPY_MODULE = "app.copy.leadership_moderation"

# The assignment roles this world plants, in `tests/fixtures/supervision.py`'s
# `ROLE_ALIASES` spelling, and the stored decider roles (ruling 4; E6-03's M2).
LEAD_FACULTY_ROLE = "LEAD_FACULTY"
CHAIR_ROLE = "CHAIR"
ASSISTANT_DEAN_ROLE = "ASSISTANT_DEAN"
AS_INSTRUCTOR = "INSTRUCTOR"
AS_LEAD_FACULTY = "LEAD_FACULTY"
AS_CHAIR = "CHAIR"

# The containment levels a second course shares with the first, as the seeding
# walker names them in a chain.
DEPARTMENT_TABLE = "department"
COLLEGE_TABLE = "college"

# The cohorts of the two courses this world adds. Both start in term week 7, the
# taught cohort's own first week, so course week N is the same term week in all
# three courses and `TERM_WEEK_OF_COURSE_WEEK` serves every one of them: `Y` runs
# eight weeks and `4` runs three (`SEEDED_COHORTS`). Neither is `F` or `Q`, which
# the report world already holds under its own course.
SIBLING_COHORT = "Y"
UNMAPPED_COHORT = "4"

# A second section of the unmapped course, planted only by
# `LeadReviewWorld.a_second_section_of_the_unmapped_course` (ruling 7, PR #296's fix
# round): a chair who teaches the cohort-`4` section needs a sibling section in the
# same course, or a rule keyed on the course rather than the section cannot be told
# apart from the right one. Every cohort starting at term week 7 is taken, so this is
# `R`, which runs twelve weeks from term week 4 (`SEEDED_COHORTS`). Term weeks 7 to
# 12 sit inside its run, so `plant(course_week=N)` still lands in term week
# `TERM_WEEK_OF_COURSE_WEEK[N]`; only the course-week number of that term week is
# different in this section, and nothing that uses it reads that number.
UNMAPPED_SECOND_COHORT = "R"

ROUTES_ARE_OWED = (
    f"E6-05's work order (decision 1) puts three routes in `{LEADERSHIP_API_MODULE}`, behind "
    "`require_leadership` (and the POST behind `csrf_verified_leadership`): `GET "
    f"…{QUEUE_ENDING}` answering the reader's queue items `{{answer_id, text, section_label}}`, "
    f"`POST …{DECISION_SEGMENT}{{answer_id}}{DECISION_ENDING}` taking an action of `exclude` "
    "or `keep` and an optional reason, and `GET "
    f"…{LOG_ENDING}` answering the exclusion log, newest first, each row carrying its stored "
    "`decision` (`EXCLUDED` or `KEPT`) as well (ruling on dispute E6-05-03)."
)

# "Send the double-submit token this session is entitled to", and "send no
# `reason` key at all" — neither can be spelled `None`, which a test sends on
# purpose. The same two sentinels `tests/fixtures/instructor_decisions.py` uses.
MINTED: Any = object()
OMITTED: Any = object()


# ---------------------------------------------------------------------------
# The routes, found in a test body (entry 44).
# ---------------------------------------------------------------------------


class LeadRoutes(NamedTuple):
    queue: str
    log: str
    decision: str


def lead_routes(application: Any) -> LeadRoutes:
    """The three routes' paths, found through the module the work order puts them in."""
    mounted = [
        route
        for route in every_route(application)
        if getattr(getattr(route, "endpoint", None), "__module__", None) == LEADERSHIP_API_MODULE
    ]

    def methods(route: Any) -> set[str]:
        return {str(method).upper() for method in (getattr(route, "methods", None) or set())}

    def path(route: Any) -> str:
        return str(getattr(route, "path", "")).rstrip("/")

    def one(found: list[Any], what: str) -> str:
        if len(found) != 1:
            pytest.fail(
                f"`{LEADERSHIP_API_MODULE}` mounts {len(found)} routes that could be {what}; the "
                f"routes it mounts are {sorted(f'{sorted(methods(r))} {path(r)}' for r in mounted)}."
                f"\n\n{ROUTES_ARE_OWED}"
            )
        return path(found[0])

    queue = one(
        [r for r in mounted if "GET" in methods(r) and path(r).endswith(QUEUE_ENDING)],
        "the queue read",
    )
    log = one(
        [r for r in mounted if "GET" in methods(r) and path(r).endswith(LOG_ENDING)],
        "the log read",
    )
    decision = one(
        [
            r
            for r in mounted
            if "POST" in methods(r)
            and DECISION_SEGMENT in path(r)
            and path(r).endswith(DECISION_ENDING)
        ],
        "the decision route",
    )
    parameters = PATH_PARAMETER.findall(decision)
    if len(parameters) != 1:
        pytest.fail(
            f"The decision route {decision!r} declares path parameters {parameters}; the work "
            "order settles exactly one, the answer id."
        )
    return LeadRoutes(queue=queue, log=log, decision=decision)


def decision_url(template: str, answer_id: Any) -> str:
    return PATH_PARAMETER.sub(lambda _match: str(answer_id), template, count=1)


# ---------------------------------------------------------------------------
# The copy the routes answer with.
# ---------------------------------------------------------------------------


def lead_moderation_copy() -> dict[str, str]:
    """Every sentence `app.copy.leadership_moderation` registers, keyed by its dotted key.

    The instructor door's device (`tests/fixtures/instructor_decisions.py::
    instructor_report_copy`), pointed at the module this ticket owns.
    """
    package = import_module(COPY_PACKAGE)
    modules = getattr(package, COPY_MODULES_FUNCTION)()
    found = [module for module in modules if getattr(module, "__name__", None) == LEAD_COPY_MODULE]
    if len(found) != 1:
        pytest.fail(
            f"`{COPY_PACKAGE}.{COPY_MODULES_FUNCTION}()` enumerates no `{LEAD_COPY_MODULE}` (it "
            f"enumerates {sorted(getattr(module, '__name__', '?') for module in modules)}). E6-05's "
            "ticket owns that module: the routes' refusal sentences live there."
        )
    mapping = getattr(found[0], COPY_MAPPING_NAME, None)
    if not isinstance(mapping, Mapping) or not mapping:
        pytest.fail(f"`{LEAD_COPY_MODULE}` publishes no `{COPY_MAPPING_NAME}` entries.")
    return {str(key): str(getattr(entry, "text", entry)) for key, entry in mapping.items()}


def lead_sentence_of(response: Any, what: str) -> str:
    """The `leadership_moderation` registry key whose sentence a response served, or a failure."""
    body = served_text(response)
    matched = sorted(
        key for key, sentence in lead_moderation_copy().items() if sentence and sentence in body
    )
    if len(matched) != 1:
        pytest.fail(
            f"{what} served {body[:400]!r}, and {len(matched)} of `{LEAD_COPY_MODULE}`'s sentences "
            f"appear in it ({matched}). Work order decision 1: the refusal is one sentence, and it "
            "lives in that module rather than inline or as a framework's own message."
        )
    return matched[0]


# ---------------------------------------------------------------------------
# Reading an answer.
# ---------------------------------------------------------------------------


def the_list_in(body: Any, what: str) -> list[Any]:
    """The list a queue or log answer carries, and nothing beside it.

    The work order settles the items and the rows and not the envelope, so a
    bare list and an object whose only member is that list are both accepted.
    **Anything else beside the list is refused**, because for the queue the
    obvious something-else is a count, which decision 1 forbids ("No week, time,
    date or count").
    """
    if isinstance(body, list):
        return body
    if isinstance(body, dict) and len(body) == 1:
        (only,) = body.values()
        if isinstance(only, list):
            return only
    pytest.fail(
        f"{what} answered {str(body)[:400]!r}. Work order decision 1 settles a list of items (or "
        "rows) and nothing else: a bare list, or an object holding that list as its only member. "
        "A second member beside it — a count, a total, a week — is the thing decision 1 forbids."
    )


def is_success(status: int) -> bool:
    """A 2xx. The work order settles the decision's effect and not its success status."""
    return 200 <= status < 300


def is_a_client_refusal(status: int) -> bool:
    return 400 <= status < 500


# ---------------------------------------------------------------------------
# The readers.
# ---------------------------------------------------------------------------


class Reader(NamedTuple):
    """One person, and the leadership session minted for them."""

    person_id: Any
    token: str
    label: str


class LeadReviewWorld:
    """The decision door's world, three courses, and a leader for each grant shape."""

    def __init__(
        self,
        door: DecisionDoor,
        committed_rows: Any,
        web_identity: Any,
        configured: Mapping[str, str],
    ) -> None:
        self.door = door
        self.rows = committed_rows
        self.web_identity = web_identity
        self.configured = configured
        self.own_course: Any = None
        self.sibling_course: Any = None
        self.unmapped_course: Any = None
        self.unmapped_course_row: Any = None
        self.department: Any = None
        self.college: Any = None
        self.lead: Reader | None = None
        self.sibling_lead: Reader | None = None
        self.chair: Reader | None = None
        self._routes: LeadRoutes | None = None

    # -- keys -----------------------------------------------------------------

    @property
    def world(self) -> Any:
        return self.door.world

    @property
    def session(self) -> Any:
        return self.door.session

    @property
    def graph(self) -> Any:
        return self.rows.graph

    @property
    def tool(self) -> Any:
        return self.door.door.tool

    @property
    def instructor_token(self) -> str:
        """The teaching instructor's own launched session — an instructor grant and nothing else."""
        return self.door.door.token

    def key(self, table: str, row: Any) -> Any:
        return row[single_primary_key(require_table(self.world.tables, table))]

    def code_of(self, cohort: str) -> str:
        """The section code this world wrote for a cohort's section (an input, not an answer)."""
        return str(self.world.section(cohort)[SECTION_CODE_COLUMN])

    def routes(self) -> LeadRoutes:
        if self._routes is None:
            self._routes = lead_routes(self.door.door.application)
        return self._routes

    # -- the sessions ---------------------------------------------------------

    def _platform_id(self) -> Any:
        registration = self.door.door.driver.registration
        return registration.platform_row[
            single_primary_key(require_table(self.world.tables, "lti_platform"))
        ]

    def minted(self, *, role: str, person_id: Any, user_id: Any, subject: str) -> str:
        """`tests/fixtures/named_sets.py::NamedSetWorld.minted`, copied (entry 37)."""
        import inspect

        import app.services.session as session_module
        from app.services.authz import Door, LandingRole

        issue = getattr(session_module, "issue_session", None)
        if not callable(issue):
            pytest.fail(
                "`app.services.session` exposes no `issue_session`. E1-08 puts the shared session "
                "module there and both doors issue through it."
            )
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
                "person and no usable `user_id`; E1-12 adds both to `SessionClaims`."
            )
        registration = self.door.door.driver.registration
        values: dict[str, Any] = {
            "door": Door.LAUNCH,
            "role": member,
            "sub": subject,
            "iss": registration.platform_row[registration.issuer_column],
            "secret": session_secret(self.configured),
            "user_id": None if user_id is None else str(user_id),
            naming_a_person[0]: None if person_id is None else str(person_id),
        }
        unfilled = [
            name
            for name, parameter in parameters.items()
            if parameter.default is parameter.empty
            and name not in values
            and parameter.kind not in (parameter.VAR_POSITIONAL, parameter.VAR_KEYWORD)
        ]
        if unfilled:
            pytest.fail(
                f"`issue_session{inspect.signature(issue)}` leaves {unfilled} for this fixture to "
                "fill and it has no value for them."
            )
        return issue(**values)

    def a_leader(
        self,
        label: str,
        *,
        grants: tuple[tuple[str, Any], ...],
        leads: tuple[Any, ...] = (),
        person_id: Any = None,
    ) -> Reader:
        """One person holding `grants` (role, scope key), leading `leads`, with a leadership session.

        A lead gets both the `LEAD_FACULTY` assignment and the
        `lead_faculty_mapping` row, because E0-11's own tests write both for a
        lead and which of the two the grant is read from is not this file's to
        guess (`tests/integration/test_the_leadership_grant_covers_no_sibling_
        leads_course.py::a_lead_of` gives the same reason).
        """
        subject = f"e6-05-{label}-{uuid4().hex[:8]}"
        person = self.web_identity.person() if person_id is None else person_id
        user_id = self.web_identity.user(platform_id=self._platform_id(), subject=subject)
        self.web_identity.link_person_to_user(person_id=person, user_id=user_id)
        for course in leads:
            self.graph.lead_mapping(person=person, course=course)
        for role, scope in grants:
            self.graph.assign(role, scope=scope, person=person)
        self.rows.commit()
        token = self.minted(
            role=LEADERSHIP_LANDING_ROLE, person_id=person, user_id=user_id, subject=subject
        )
        return Reader(person_id=person, token=token, label=label)

    def a_lead_of(self, label: str, course: Any) -> Reader:
        return self.a_leader(label, grants=((LEAD_FACULTY_ROLE, course),), leads=(course,))

    def a_leadership_session_for_the_instructor(self) -> str:
        """A `LEADERSHIP` session naming the door's instructor, who holds no leadership grant."""
        from fixtures.web_identity import USER_ID_CLAIM, claims_in_session

        claims = claims_in_session(self.instructor_token)
        subject = claims.get("sub")
        assert (
            isinstance(subject, str) and subject
        ), f"The instructor's launched session carries no `sub` (it carries {sorted(claims)})."
        return self.minted(
            role=LEADERSHIP_LANDING_ROLE,
            person_id=self.door.person_id,
            user_id=claims.get(USER_ID_CLAIM),
            subject=subject,
        )

    def another_sessions_csrf_token(self, token: str) -> str:
        """A genuine double-submit token bound to a session that is not `token`'s."""
        secret = session_secret(self.configured)
        another = issue_student_session(
            secret=secret,
            issuer="https://e6-05-another-origin.invalid",
            subject=f"e6-05-another-session-{uuid4().hex}",
            user_id=uuid4(),
        )
        forged = csrf_token_for(another, secret)
        assert forged != csrf_token_for(token, secret), (
            "Two sessions' CSRF tokens are the same string, so the forged case carries no other "
            "session's token at all."
        )
        return forged

    # -- asking ---------------------------------------------------------------

    def ask(self, method: str, url: str, *, token: Any, json: Any = None) -> Any:
        """One request carrying exactly `token` as a Bearer header and no cookie."""
        headers: dict[str, str] = {}
        if token is not None:
            headers["authorization"] = f"{AUTHENTICATE_SCHEME} {token}"
        with self.door.door.carrying_no_cookie():
            return self.tool.request(method, url, headers=headers, json=json)

    def queue(self, reader: Any) -> Any:
        return self.ask("GET", self.routes().queue, token=_token(reader))

    def log(self, reader: Any) -> Any:
        return self.ask("GET", self.routes().log, token=_token(reader))

    def body(self, action: str, reason: Any) -> dict[str, Any]:
        sent: dict[str, Any] = {ACTION_FIELD: action}
        if reason is not OMITTED:
            sent["reason"] = reason
        return sent

    def decide(self, reader: Any, answer_id: Any, action: str, reason: Any = None) -> Any:
        url = decision_url(self.routes().decision, answer_id)
        return self.ask("POST", url, token=_token(reader), json=self.body(action, reason))

    def decide_as_a_browser(
        self,
        reader: Reader,
        answer_id: Any,
        action: str,
        reason: Any = None,
        *,
        csrf_token: Any = MINTED,
    ) -> Any:
        """One decision with the session in the cookie and no `Authorization` header.

        `tests/fixtures/instructor_decisions.py::DecisionDoor.decide_as_a_browser`,
        copied (entry 37): the jar is cleared, filled and cleared again on the
        client itself.
        """
        secret = session_secret(self.configured)
        session_cookie, csrf_cookie = session_cookie_names()
        headers: dict[str, str] = {}
        cookies = {session_cookie: reader.token}
        if csrf_token is not None:
            value = csrf_token_for(reader.token, secret) if csrf_token is MINTED else csrf_token
            cookies[csrf_cookie] = value
            headers[CSRF_HEADER] = value
        url = decision_url(self.routes().decision, answer_id)
        tool = self.tool
        tool.cookies.clear()
        try:
            for name, value in cookies.items():
                tool.cookies.set(name, value)
            return tool.post(url, json=self.body(action, reason), headers=headers)
        finally:
            tool.cookies.clear()

    def items(self, reader: Reader) -> list[dict[str, Any]]:
        """The reader's queue items, after requiring a 200."""
        answered = self.queue(reader)
        assert answered.status_code == 200, (
            f"The queue answered {answered.status_code} to {reader.label}, a leadership session "
            f"holding a grant. Body begins {answered.text[:400]!r}.\n\n{ROUTES_ARE_OWED}"
        )
        return the_list_in(answered.json(), f"The queue read for {reader.label}")

    def log_rows(self, reader: Reader) -> list[dict[str, Any]]:
        """The reader's log rows, after requiring a 200."""
        answered = self.log(reader)
        assert answered.status_code == 200, (
            f"The log answered {answered.status_code} to {reader.label}, a leadership session "
            f"holding a grant. Body begins {answered.text[:400]!r}.\n\n{ROUTES_ARE_OWED}"
        )
        return the_list_in(answered.json(), f"The log read for {reader.label}")

    def queued_ids(self, reader: Reader) -> set[str]:
        return {str(item.get(ITEM_ANSWER_ID)) for item in self.items(reader)}

    # -- planting -------------------------------------------------------------

    def plant(
        self,
        *,
        course_week: int,
        stream: str,
        text: str,
        verdict: Any,
        cohort: str,
    ) -> Any:
        """One comment through the decision door's own planter; its answer id."""
        return self.door.plant_a_comment(
            course_week=course_week, stream=stream, text=text, verdict=verdict, cohort=cohort
        )

    def rows_of(self, answer_id: Any) -> list[dict[str, Any]]:
        return self.door.rows(answer_id)

    def plant_decision(
        self,
        answer_id: Any,
        state: str,
        *,
        decided_by: Any,
        decided_as: str,
        reason: Any = None,
        decided_at: datetime | None = None,
    ) -> None:
        """One decision row another door wrote, every value named by the caller."""
        require_decision_columns(self.world.tables)
        values: dict[str, Any] = {
            ANSWER_COLUMN: answer_id,
            STATE_COLUMN: state,
            DECIDER_COLUMN: decided_by,
            DECIDED_AS_COLUMN: decided_as,
            REASON_COLUMN: reason,
        }
        if decided_at is not None:
            values[decided_at_column(self.world.tables)] = decided_at
        self.world.seed("moderation_state", {}, **values)
        self.door.door.commit()

    def a_second_section_of_the_unmapped_course(self) -> Any:
        """Seed a cohort-`UNMAPPED_SECOND_COHORT` section in the unmapped course; its key.

        The chain is swapped for a copy whose course is the unmapped course and
        which holds no section, so the walker seeds the section under that course,
        and is put back afterwards: `_a_course_beside_the_own_one`'s device, with
        the course kept instead of popped. **The premise check is this fixture's**:
        the new section's course is read back from its row, so a section that
        landed anywhere else is a broken world, not a red.
        """
        world = self.world
        calendar = world.calendar
        saved = calendar.chain
        branch = dict(saved)
        branch.pop(SECTION_TABLE, None)
        branch[COURSE_TABLE] = self.unmapped_course_row
        calendar.chain = branch
        try:
            section = world.section(UNMAPPED_SECOND_COHORT)
        finally:
            calendar.chain = saved
        self.rows.commit()
        course_of_section = section[world.link(SECTION_TABLE, COURSE_TABLE)]
        assert str(course_of_section) == str(self.unmapped_course), (
            f"The cohort-{UNMAPPED_SECOND_COHORT} section was seeded in course {course_of_section}, "
            f"not in the unmapped course {self.unmapped_course}. A broken world, not a red."
        )
        return world.section_id(UNMAPPED_SECOND_COHORT)

    def teaches(self, reader: Reader, cohort: str) -> None:
        """Give `reader` an `INSTRUCTOR` assignment on the cohort's section, beside their grants.

        `tests/integration/test_the_lead_review_queue_and_log_never_cross_to_a_
        sibling_lead.py`'s second hat, as a method. The assignment is read
        back: a reader who still holds only their leadership grant afterwards is a
        broken world, and a test using it would be the plain one-hat test again.
        """
        before = len(self.graph.assignments_of(reader.person_id))
        section = self.world.section_id(cohort)
        self.graph.assign(INSTRUCTOR_ROLE, scope=section, person=reader.person_id)
        self.rows.commit()
        after = len(self.graph.assignments_of(reader.person_id))
        assert after == before + 1, (
            f"{reader.label} held {before} assignments and holds {after} after being given an "
            f"instructor assignment on the cohort-{cohort} section."
        )


def _token(reader: Any) -> Any:
    return reader.token if isinstance(reader, Reader) else reader


def _a_course_beside_the_own_one(world: Any, cohort: str) -> Any:
    """A new course under the report world's own prefix, with one section of `cohort`.

    The report world's calendar seeds every section under its one chain, so the
    chain is swapped for a copy without its course and section while the section
    is seeded — the walker then invents a course under the same prefix — and put
    back afterwards. Popping exactly those two levels is
    `tests/fixtures/named_sets.py::build_named_set_world`'s invocation.
    """
    calendar = world.calendar
    saved = calendar.chain
    branch = dict(saved)
    for level in (SECTION_TABLE, COURSE_TABLE):
        branch.pop(level, None)
    calendar.chain = branch
    try:
        world.section(cohort)
    finally:
        calendar.chain = saved
    if COURSE_TABLE not in branch:
        pytest.fail(
            f"Seeding a cohort-{cohort} section on a chain without a course left no `{COURSE_TABLE}` "
            f"in it ({sorted(branch)}), so this world cannot say which course the section is in."
        )
    return branch[COURSE_TABLE]


def build_lead_review_world(
    door: DecisionDoor,
    committed_rows: Any,
    web_identity: Any,
    configured: Mapping[str, str],
) -> LeadReviewWorld:
    """Add the sibling and unmapped courses and the three leaders to the decision door's world.

    **The premise checks at the foot are this fixture's.** They are claims about
    the rows written here — three distinct courses, all under one prefix and one
    department — and not about anything E6-05 owes, so a failure in them is a
    defect in this world (`docs/MISTAKES.md` entry 13). Without them, a sibling
    "refused" because it sat in another department would prove nothing about a
    lead's grant.
    """
    review = LeadReviewWorld(door, committed_rows, web_identity, configured)
    world = door.world
    chain = world.calendar.chain
    levels = (COURSE_TABLE, PREFIX_TABLE, DEPARTMENT_TABLE, COLLEGE_TABLE)
    missing = [level for level in levels if level not in chain]
    if missing:
        pytest.fail(
            f"The report world's containment chain holds {sorted(chain)} and lacks {missing}; this "
            "world needs the course, prefix, department and college the report world sits in."
        )
    own = chain[COURSE_TABLE]
    sibling = _a_course_beside_the_own_one(world, SIBLING_COHORT)
    unmapped = _a_course_beside_the_own_one(world, UNMAPPED_COHORT)
    committed_rows.commit()

    review.own_course = review.key(COURSE_TABLE, own)
    review.sibling_course = review.key(COURSE_TABLE, sibling)
    review.unmapped_course = review.key(COURSE_TABLE, unmapped)
    review.unmapped_course_row = unmapped
    review.department = review.key(DEPARTMENT_TABLE, chain[DEPARTMENT_TABLE])
    review.college = review.key(COLLEGE_TABLE, chain[COLLEGE_TABLE])

    courses = {review.own_course, review.sibling_course, review.unmapped_course}
    assert len(courses) == 3, f"The three courses of this world are not three rows: {courses}."
    prefix_key = single_primary_key(require_table(world.tables, PREFIX_TABLE))
    prefix_link = next(
        (
            column.name
            for column in require_table(world.tables, COURSE_TABLE).columns
            if any(key.column.table.name == PREFIX_TABLE for key in column.foreign_keys)
        ),
        None,
    )
    assert prefix_link is not None, "`course` carries no foreign key to `prefix`."
    prefixes = {str(row[prefix_link]) for row in (own, sibling, unmapped)}
    assert prefixes == {str(chain[PREFIX_TABLE][prefix_key])}, (
        f"The three courses sit under prefixes {prefixes}, not under the report world's one prefix. "
        "A sibling under another prefix is not a sibling, and a refusal of it could be explained "
        "by the containment tree rather than by a lead's grant."
    )

    review.lead = review.a_lead_of("the-lead", review.own_course)
    review.sibling_lead = review.a_lead_of("the-sibling-lead", review.sibling_course)
    review.chair = review.a_leader("the-chair", grants=((CHAIR_ROLE, review.department),))
    return review


@pytest.fixture
def lead_review(
    decision_door: DecisionDoor,
    committed_rows: Any,
    web_identity: Any,
    configured_env: dict[str, str],
) -> LeadReviewWorld:
    """The decision door's world with a lead, a sibling lead and a chair. See the module docstring.

    Builds nothing E6-05 owes: the routes are looked up inside each test body, so
    an unbuilt tree is a FAILED naming them (`docs/MISTAKES.md` entry 44).
    """
    return build_lead_review_world(decision_door, committed_rows, web_identity, configured_env)
