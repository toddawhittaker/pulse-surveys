"""E6-03 — the instructor's decision door, the comments a test decides on, and the rows it leaves.

Seven test modules need the same handful of things, and nothing in this repository
answers them yet:

  - **The decision route, found rather than spelled.** E6-03's work order
    (decision 1) settles `POST …/comments/{answer_id}/decisions` "matching the
    prefix `api/instructor.py` already uses for its paths", and settles the module.
    So the route is the one `POST` that module mounts whose path ends in
    `/decisions` under a `/comments/` segment — the device
    `tests/fixtures/report_api.py` uses for E4-07's two `GET` routes — and the one
    path parameter it declares is filled with the answer id, whatever it is
    called. The body is the work order's: `{"action": …, "reason": …}`.
  - **A comment planted where the test needs it**, in the canonical report world
    `tests/fixtures/report_api.py` builds: a new respondent per comment, a
    moderation verdict the test chooses, routed through the product's own writer
    after the window has closed (`tests/fixtures/moderation.py`).
  - **The rows a decision leaves**, read back on the bootstrap connection in the
    order E6-01's `sequence` column gives them.
  - **The governed sentences.** Every refusal the door answers is a sentence in
    `backend/app/copy/instructor_report.py` (work order decision 1); a served
    body is matched against that module's registry entries and nothing else.

**Nothing here decides what the door should answer.** It plants rows, makes
requests and reads rows; every expectation is written out in the test that makes it
(`docs/MISTAKES.md` entries 19 and 30). The one value this file writes into the
database on a test's behalf — a decision row a person other than the door made —
is named by the test that plants it, column by column.

**Every guard is a plain function called from a test body** (`docs/MISTAKES.md`
entry 44): on a tree where E6-03 is unbuilt, a test fails naming the missing
route, column or copy module rather than erroring at setup.
"""

from collections.abc import Mapping
from importlib import import_module
from typing import Any
from uuid import uuid4

import pytest
from sqlalchemy import select

from fixtures.grading import RESPONSE_SECTION_COLUMN, RESPONSE_WEEK_COLUMN
from fixtures.moderation import moderation_states
from fixtures.report_api import (
    ANSWER_ID_FIELD,
    COMMENTS_FIELD,
    INSTRUCTOR_API_MODULE,
    PATH_PARAMETER,
    PAYLOAD_STREAM_KEY,
    RATING_POSITION,
    RELEASED_MEMBER,
    STREAMS_MEMBER,
    TAUGHT_COHORT,
    TERM_WEEK_OF_COURSE_WEEK,
    ReportDoor,
)
from fixtures.report_views import COURSE_STREAM, INSTRUCTOR_STREAM
from fixtures.routing import every_route
from fixtures.submit import (
    ANSWER_TABLE,
    COMMENT_TEXT_COLUMN,
    COPY_MAPPING_NAME,
    COPY_MODULES_FUNCTION,
    COPY_PACKAGE,
    CSRF_HEADER,
    RESPONSE_TABLE,
    csrf_token_for,
    issue_student_session,
    served_text,
    session_cookie_names,
    session_secret,
)
from fixtures.supervision import require_table, single_primary_key

# ---------------------------------------------------------------------------
# The names E6-03's ticket and work order settle, spelled once.
# ---------------------------------------------------------------------------

# Work order decision 1: the route and its body.
COMMENTS_SEGMENT = "comments"
DECISIONS_SEGMENT = "decisions"
ACTION_FIELD = "action"
REASON_FIELD = "reason"
EXCLUDE = "exclude"
KEEP = "keep"
UNDO = "undo"

# Work order decision 1's statuses.
OK = 200
NOT_FOUND = 404
CONFLICT = 409
UNPROCESSABLE = 422

# The ticket's "Owns": the refusal sentences live here.
INSTRUCTOR_COPY_MODULE = "app.copy.instructor_report"

# The ticket's M2 and the work order's decisions 3 to 5: the decision columns on
# `moderation_state`, the role vocabulary, and the reason's bound.
MODERATION_STATE_TABLE = "moderation_state"
ANSWER_COLUMN = "answer_id"
STATE_COLUMN = "state"
SEQUENCE_COLUMN = "sequence"
DECIDER_COLUMN = "decided_by_person_id"
DECIDED_AS_COLUMN = "decided_as"
REASON_COLUMN = "reason"
IS_UNDO_COLUMN = "is_undo"
DECISION_COLUMNS = (DECIDER_COLUMN, DECIDED_AS_COLUMN, REASON_COLUMN, IS_UNDO_COLUMN)

AS_INSTRUCTOR = "INSTRUCTOR"
AS_LEAD_FACULTY = "LEAD_FACULTY"
AS_CHAIR = "CHAIR"
DECIDER_ROLES = (AS_INSTRUCTOR, AS_LEAD_FACULTY, AS_CHAIR)

REASON_BOUND = 500

# E4-02's stored states (`tests/integration/test_report_schema.py`).
STORED_PUBLISHED = "PUBLISHED"
STORED_FLAGGED = "FLAGGED_COLLAPSED"
STORED_EXCLUDED = "EXCLUDED"
STORED_KEPT = "KEPT"

# What the payload reports for each, E4-04's spelling (`tests/fixtures/report_comments.py`).
PUBLISHED = "published"
FLAGGED = "flagged_collapsed"
EXCLUDED = "excluded"
KEPT = "kept"

M2_IS_OWED = (
    "E6-03's migration (M2) adds to `moderation_state`: `decided_by_person_id` (nullable, a `person` "
    "foreign key with `RESTRICT`), `decided_as` (the role the decision was made under — "
    "`INSTRUCTOR`, `LEAD_FACULTY` or `CHAIR`), `reason` (nullable; non-blank and at most 500 "
    "characters when present) and `is_undo` (`boolean NOT NULL DEFAULT false`), with `CHECK`s "
    "tying them to the state."
)

DECISION_ROUTE_IS_OWED = (
    f"E6-03's work order (decision 1) puts one `POST …/{COMMENTS_SEGMENT}/{{answer_id}}/"
    f"{DECISIONS_SEGMENT}` in `{INSTRUCTOR_API_MODULE}`, under the prefix that module already uses, "
    'taking `{"action": "exclude" | "keep" | "undo", "reason": str | null}`, guarded by '
    "the new `csrf_verified_instructor`, and answering 200 with the comment's new `CommentView`."
)


# ---------------------------------------------------------------------------
# Guards, called as a test's first statement (entry 44).
# ---------------------------------------------------------------------------


def require_decision_columns(tables: Mapping[str, Any]) -> Any:
    """`moderation_state` with M2's four columns, or a failure naming them."""
    table = require_table(dict(tables), MODERATION_STATE_TABLE)
    missing = [column for column in DECISION_COLUMNS if column not in table.c]
    if missing:
        pytest.fail(
            f"`{MODERATION_STATE_TABLE}` declares no {missing}; it declares "
            f"{[column.name for column in table.columns]}. {M2_IS_OWED}"
        )
    return table


def decision_route(application: Any) -> str:
    """The decision route's path template, found through the module that owns it."""
    posts = [
        route
        for route in every_route(application)
        if "POST" in (getattr(route, "methods", None) or set())
        and getattr(getattr(route, "endpoint", None), "__module__", None) == INSTRUCTOR_API_MODULE
    ]
    found = [
        route
        for route in posts
        if str(getattr(route, "path", "")).rstrip("/").endswith(f"/{DECISIONS_SEGMENT}")
        and f"/{COMMENTS_SEGMENT}/" in str(getattr(route, "path", ""))
    ]
    if len(found) != 1:
        pytest.fail(
            f"`{INSTRUCTOR_API_MODULE}` mounts {len(found)} decision routes; the POST routes it "
            f"mounts are {sorted(str(getattr(route, 'path', '?')) for route in posts)}.\n\n"
            f"{DECISION_ROUTE_IS_OWED}"
        )
    template = str(found[0].path)
    parameters = PATH_PARAMETER.findall(template)
    if len(parameters) != 1:
        pytest.fail(
            f"The decision route {template!r} declares path parameters {parameters}; the work order "
            "settles exactly one, the answer id."
        )
    return template


def decision_url(template: str, answer_id: Any) -> str:
    """The template with its one parameter filled with `answer_id`."""
    return PATH_PARAMETER.sub(lambda _match: str(answer_id), template, count=1)


def instructor_report_copy() -> dict[str, str]:
    """Every sentence `app.copy.instructor_report` registers, keyed by its dotted key."""
    package = import_module(COPY_PACKAGE)
    modules = getattr(package, COPY_MODULES_FUNCTION)()
    found = [
        module for module in modules if getattr(module, "__name__", None) == INSTRUCTOR_COPY_MODULE
    ]
    if len(found) != 1:
        pytest.fail(
            f"`{COPY_PACKAGE}.{COPY_MODULES_FUNCTION}()` enumerates no `{INSTRUCTOR_COPY_MODULE}` "
            f"(it enumerates {sorted(getattr(module, '__name__', '?') for module in modules)}). E6-03 "
            "puts every refusal sentence of the decision route there."
        )
    mapping = getattr(found[0], COPY_MAPPING_NAME, None)
    if not isinstance(mapping, Mapping) or not mapping:
        pytest.fail(f"`{INSTRUCTOR_COPY_MODULE}` publishes no `{COPY_MAPPING_NAME}` entries.")
    return {str(key): str(getattr(entry, "text", entry)) for key, entry in mapping.items()}


def governed_sentence_of(response: Any, what: str) -> str:
    """The `instructor_report` registry key whose sentence a response served, or a failure."""
    body = served_text(response)
    matched = sorted(
        key for key, sentence in instructor_report_copy().items() if sentence and sentence in body
    )
    if len(matched) != 1:
        pytest.fail(
            f"{what} served {body[:400]!r}, and {len(matched)} of `{INSTRUCTOR_COPY_MODULE}`'s "
            f"sentences appear in it ({matched}). E6-03's work order: each refusal sentence lives in "
            "that module, so the route serves one of them and never an inline string or a "
            "framework's own validation message."
        )
    return matched[0]


# ---------------------------------------------------------------------------
# The door.
# ---------------------------------------------------------------------------

# "Send the double-submit token this session is entitled to", and "send no
# `reason` key at all" — neither can be spelled `None`, which is a value a test
# sends on purpose.
MINTED: Any = object()
OMITTED: Any = object()


class DecisionDoor:
    """The teaching instructor's report door, with the decision route beside its reads."""

    def __init__(self, door: ReportDoor, configured: Mapping[str, str] | None = None) -> None:
        self.door = door
        self.configured = configured
        self._template: str | None = None
        self._planted = 0

    @property
    def world(self) -> Any:
        return self.door.world

    @property
    def session(self) -> Any:
        return self.door.world.session

    @property
    def person_id(self) -> Any:
        """The `person` the instructor's session names — the decider every decision should name."""
        return self.door.person_id

    def template(self) -> str:
        if self._template is None:
            self._template = decision_route(self.door.application)
        return self._template

    # -- asking ---------------------------------------------------------------

    def body(self, action: str, reason: Any) -> dict[str, Any]:
        sent: dict[str, Any] = {ACTION_FIELD: action}
        if reason is not OMITTED:
            sent[REASON_FIELD] = reason
        return sent

    def decide(self, answer_id: Any, action: str, reason: Any = None) -> Any:
        """One decision, the session carried as a Bearer header (the SPA's path, ADR 0089)."""
        url = decision_url(self.template(), answer_id)
        with self.door.carrying_no_cookie():
            return self.door.tool.post(
                url, json=self.body(action, reason), headers=self.door.credential()
            )

    def decide_as_a_browser(
        self, answer_id: Any, action: str, reason: Any = None, *, csrf_token: Any = MINTED
    ) -> Any:
        """One decision with the session in the **cookie** and no `Authorization` header.

        `tests/fixtures/named_sets.py::NamedSetDoor.create_as_a_browser`'s
        invocation, copied rather than adapted (`docs/MISTAKES.md` entry 37): the
        jar is cleared, filled and cleared again on the client itself. `csrf_token`
        is `MINTED` for the token this session is entitled to, `None` for no CSRF
        pair at all, or a string sent as the cookie *and* the header.
        """
        secret = self.secret()
        session_cookie, csrf_cookie = session_cookie_names()
        headers: dict[str, str] = {}
        cookies = {session_cookie: self.door.token}
        if csrf_token is not None:
            value = csrf_token_for(self.door.token, secret) if csrf_token is MINTED else csrf_token
            cookies[csrf_cookie] = value
            headers[CSRF_HEADER] = value
        url = decision_url(self.template(), answer_id)
        tool = self.door.tool
        tool.cookies.clear()
        try:
            for name, value in cookies.items():
                tool.cookies.set(name, value)
            return tool.post(url, json=self.body(action, reason), headers=headers)
        finally:
            tool.cookies.clear()

    def secret(self) -> bytes:
        if self.configured is None:
            pytest.fail(
                "This door was built without the configured mapping, so it cannot mint a CSRF "
                "token. Pass `configured_env` to `DecisionDoor`."
            )
        return session_secret(self.configured)

    def another_sessions_csrf_token(self) -> str:
        """A genuine double-submit token, bound to a session that is not this door's.

        What a page on another origin can come by: a token the application's own
        primitive minted, for a session of its own. A check that tests for presence,
        or compares the cookie to the header, passes it; only verification against
        *this* session's `jti` refuses it (`docs/disputes/E2-08-06.md`).
        """
        secret = self.secret()
        another = issue_student_session(
            secret=secret,
            issuer="https://e6-03-another-origin.invalid",
            subject=f"e6-03-another-session-{uuid4().hex}",
            user_id=uuid4(),
        )
        forged = csrf_token_for(another, secret)
        assert forged != csrf_token_for(self.door.token, secret), (
            "Two sessions' CSRF tokens are the same string, so the forged case carries no other "
            "session's token at all."
        )
        return forged

    # -- reading --------------------------------------------------------------

    def rows(self, answer_id: Any) -> list[dict[str, Any]]:
        """Every `moderation_state` row for one answer, in insertion order, as stored."""
        self.door.refresh()
        found = moderation_states(self.session, answer_id)
        if found and SEQUENCE_COLUMN not in found[0]:
            pytest.fail(f"`{MODERATION_STATE_TABLE}` rows carry no `{SEQUENCE_COLUMN}` (E6-01).")
        return sorted(found, key=lambda row: row[SEQUENCE_COLUMN])

    def payload(self, course_week: int) -> Any:
        body, _answered = self.door.payload(course_week=course_week)
        return body

    def cards(self, body: Any) -> list[dict[str, Any]]:
        """Every comment object in one payload: both streams' lists and the released list."""
        found: list[dict[str, Any]] = []
        streams = body.get(STREAMS_MEMBER) or {}
        for stream in (INSTRUCTOR_STREAM, COURSE_STREAM):
            found.extend((streams.get(PAYLOAD_STREAM_KEY[stream]) or {}).get(COMMENTS_FIELD) or [])
        found.extend(body.get(RELEASED_MEMBER) or [])
        return found

    def card(self, body: Any, answer_id: Any) -> dict[str, Any] | None:
        """The comment object carrying `answer_id` as its handle, or `None`."""
        matched = [
            card for card in self.cards(body) if str(card.get(ANSWER_ID_FIELD)) == str(answer_id)
        ]
        assert len(matched) <= 1, f"The payload carries {len(matched)} cards for one answer."
        return matched[0] if matched else None

    # -- planting -------------------------------------------------------------

    def plant_a_comment(
        self,
        *,
        course_week: int,
        stream: str,
        text: str,
        verdict: str | None,
        cohort: str = TAUGHT_COHORT,
    ) -> Any:
        """One new respondent's comment, with the moderation verdict the test chose; its answer id.

        A new respondent each time, because E2-05 holds one response per student
        per section-week. Committed, because the tool connects for itself.
        """
        self._planted += 1
        world = self.world
        student = world.student(
            f"e6-03-respondent-{self._planted}-{uuid4().hex[:8]}", cohorts=(cohort,)
        )
        _response, written = world.submit(
            term_week=TERM_WEEK_OF_COURSE_WEEK[course_week],
            comments={stream: text},
            ratings={RATING_POSITION[stream]: 4},
            cohort=cohort,
            student=student,
            moderation={stream: verdict},
        )
        self.door.commit()
        return world.answer_key(written[stream])

    def answer_id_of(self, text: str) -> Any:
        """The one `answer` row carrying `text`, by key."""
        answers = require_table(self.world.tables, ANSWER_TABLE)
        key = single_primary_key(answers)
        found = list(
            self.session.execute(
                select(answers.c[key]).where(answers.c[COMMENT_TEXT_COLUMN] == text)
            ).scalars()
        )
        assert len(found) == 1, f"{len(found)} answers carry {text!r}; this world planted one."
        return found[0]

    def a_rating_answer_in(self, course_week: int, cohort: str = TAUGHT_COHORT) -> Any:
        """One `answer` row of the section-week that carries no comment text — not a comment."""
        answers = require_table(self.world.tables, ANSWER_TABLE)
        responses = require_table(self.world.tables, RESPONSE_TABLE)
        answer_key = single_primary_key(answers)
        response_key = single_primary_key(responses)
        link = self.world.link(ANSWER_TABLE, RESPONSE_TABLE)
        found = list(
            self.session.execute(
                select(answers.c[answer_key])
                .select_from(answers.join(responses, answers.c[link] == responses.c[response_key]))
                .where(
                    responses.c[RESPONSE_SECTION_COLUMN] == self.world.section_id(cohort),
                    responses.c[RESPONSE_WEEK_COLUMN]
                    == self.world.week_id(TERM_WEEK_OF_COURSE_WEEK[course_week]),
                    answers.c[COMMENT_TEXT_COLUMN].is_(None),
                )
            ).scalars()
        )
        assert found, f"Course week {course_week} holds no answer without comment text."
        return found[0]

    def a_person(self) -> Any:
        """A `person` who is not the door's instructor, by key."""
        person = self.world.seed("person", {})
        self.door.commit()
        return person[self.world.key_of("person")]

    def plant_a_decision(
        self, answer_id: Any, state: str, *, decided_by: Any, decided_as: str, reason: Any = None
    ) -> None:
        """One decision row another door wrote, every decision column named by the caller."""
        require_decision_columns(self.world.tables)
        values: dict[str, Any] = {
            ANSWER_COLUMN: answer_id,
            STATE_COLUMN: state,
            DECIDER_COLUMN: decided_by,
            DECIDED_AS_COLUMN: decided_as,
            REASON_COLUMN: reason,
        }
        self.world.seed(MODERATION_STATE_TABLE, {}, **values)
        self.door.commit()


@pytest.fixture
def decision_door(report_door: ReportDoor, configured_env: dict[str, str]) -> DecisionDoor:
    """The teaching instructor at the report door, with the decision route beside it.

    Builds nothing E6-03 owes: the world and the launch are E4-07's
    (`report_door`), and the route is looked up inside each test body, so an
    unbuilt tree is a FAILED naming the route rather than an ERROR at setup
    (`docs/MISTAKES.md` entry 44). `configured_env` is the mapping the door's
    application was built under, which is where the CSRF secret is read from
    (`docs/MISTAKES.md` entry 40).
    """
    return DecisionDoor(report_door, configured_env)


def latest(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """The last row of a non-empty, insertion-ordered list."""
    assert rows, "There are no `moderation_state` rows to read the latest of."
    return rows[-1]


def a_reason(length: int, *, pad: str = "") -> str:
    """A reason of exactly `length` non-blank characters, with `pad` on either side.

    No whitespace inside, so a reason that is trimmed for storage and one stored as
    sent are the same string, and a test comparing what was stored against what was
    sent is about the bound rather than about whitespace.
    """
    body = ("Unflagged-exclusion-reason." * (length // 27 + 1))[:length]
    return f"{pad}{body}{pad}"
