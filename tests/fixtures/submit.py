"""E2-08 — the world a student submits into, and the tool they submit through.

Five test modules need the same three things: a committed section with an open
survey window and the v1 question set behind it, a signed-in student the
application can resolve, and a running tool whose AI provider address the test
chose. A copy of any of them in each module is `docs/MISTAKES.md` entry 13, so
all three live here.

**What this file decides, and what it refuses to.** Everything below that names a
table, a column, a status or a copy key is transcribed from E2-05's schema, from
ADR 0056's taxonomy or from E2-08's own work order, and every one of those is
settled. Two things are **not** settled by the ticket and are marked where they
appear, so that a ruling is a one-line change here rather than a rewrite:

  - **The request body.** The route's *path* is discovered (`submit_route` below
    finds the one `POST` route `app.api.student` defines, which is the module
    E2-08's work order settles), but nothing settles the JSON a submission is
    spelled in. `submission_body` builds the least-invented shape available: the
    value keys are `answer`'s own column names, which E2-05 settled, and the
    ordinal is `question.position`, which E2-05 settled too. Only the envelope —
    a list under `answers` — is this suite's choice.
  - **The status a bounce answers with.** The work order settles 401, 403, 404,
    409, 422 and 503 for the refusals it names, and an `insufficient` or
    `nonsense` verdict is not among them. So the bounce tests assert what the
    criterion says — a client error, the registry's coaching text, nothing
    stored — and deliberately do not pin the number.

**Nothing here asserts what the submit path answers.** These fixtures seed rows,
build a client and read rows back; what a submission produces is each test
module's subject, and a fixture that encoded it would be a second implementation
for the tests to agree with (`docs/MISTAKES.md` entry 30).

**The environment** (`docs/MISTAKES.md` entry 40): `open_submit_tool` states
`ENVIRONMENT`, `INSTITUTION_TIMEZONE`, `MOCK_AI_PROVIDER_BASE_URL` and
`REDIS_URL` itself, on top of `configured_env`'s documented file, and rides
`tool_doors` for the container's database coordinates. Nothing here reads
`os.environ` except for the session secret, which is read back out of the same
documented mapping the application was built from.

**The provider address is the mock's, and the ruling rather than the endpoint is
what decides that.** The configuration split of 2026-09-02 gives the real
provider and the in-repo mock a triple each and settles selection:
`AIGateway(live=False)` reads `MOCK_AI_PROVIDER_*` in development and test.
`open_submit_tool` states `ENVIRONMENT=development` in its own body, so the
variable the tool it builds will consult is the mock's — whatever is listening on
the other end, and including the closed port `unreachable_ai_provider` hands it.
That case is about what the application does when *its* provider is unreachable,
and in a test process its provider is the mock triple.

**The broker is pointed at a closed port by default, and that is deliberate.**
`.env.example` names the Compose service `redis`, which does not resolve here, so
every submission would enqueue against a name lookup that fails on its own
schedule. A closed loopback port refuses immediately, which is the background
`docs/MISTAKES.md` entry 41's near-miss has to be measured against: the request
is required to be *prompt* when the broker is down, and a slow refusal would hide
a slow enqueue.
"""

import re
import socket
import time
from collections.abc import Callable, Mapping
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any, NamedTuple

import pytest
from sqlalchemy import Enum as SqlEnum

from fixtures.celery_broker import REDIS_URL_VARIABLE
from fixtures.clock import DEVELOPMENT, ENVIRONMENT_VARIABLE, INSTITUTION_TIMEZONE_VARIABLE
from fixtures.doors import (
    PLATFORM_AUTHORIZATION_ENDPOINT_COLUMNS,
    PLATFORM_CLIENT_ID_COLUMNS,
    PLATFORM_ISSUER_COLUMNS,
    PLATFORM_JWKS_URL_COLUMNS,
    door_column_named,
)
from fixtures.mock_ai import MOCK_AI_PROVIDER_BASE_URL_VARIABLE
from fixtures.routing import every_route
from fixtures.supervision import foreign_key_columns, require_table, single_primary_key
from fixtures.survey_windows import (
    COHORT_SECTION_MODALITY,
    COHORT_SECTION_ORDINAL,
    FALL_2026_TERM_END,
    FALL_2026_TERM_START,
    FALL_2026_TERM_WEEKS,
    INSTITUTION_TIMEZONE,
    SEEDED_COHORTS,
)

# ---------------------------------------------------------------------------
# The names E2-08's work order settles.
# ---------------------------------------------------------------------------

# SPEC §13's tree gives the route module and the service module, and the work
# order names both: "the submit route goes in a new file `backend/app/api/
# student.py`", "synchronous gating logic goes in new
# `backend/app/services/validity.py`". The first is how the route is *found* —
# see `submit_route` — so it is a settled fact this file rests on rather than a
# spelling it invented.
STUDENT_API_MODULE = "app.api.student"
VALIDITY_SERVICE_MODULE = "app.services.validity"

# The copy package the work order settles, and the two keys it spells out.
# Everything else the registry holds is asserted by *role* rather than by key —
# the route serves a string, and the string has to be one the registry publishes
# — because the work order names the surfaces and not their key names.
COPY_PACKAGE = "app.copy"
SUBMIT_COPY_MODULE = "app.copy.submit"
COPY_ENTRY_CLASS = "CopyEntry"
COPY_MODULES_FUNCTION = "copy_modules"
COPY_MAPPING_NAME = "COPY"
NOT_A_STUDENT_KEY = "student.not_a_student"
CLASSIFIER_DOWN_KEY = "submit.classifier_down"

# The third key spelled by a record rather than by role, and the only one settled
# after these tests were written:
# [ADR 0115](../../docs/adr/0115-a-resubmission-revises-its-answers-in-place.md)
# refuses the withdrawal of a comment a classification names, "with its own
# reason and its own sentence (`submit.comment_already_judged`, HTTP 409), rather
# than left to surface as a constraint error under a student".
COMMENT_ALREADY_JUDGED_KEY = "submit.comment_already_judged"

# The work order's refusal statuses. Each is settled there by name:
# "refusals are HTTP 422 for missing-required/out-of-range/off-step ..., 409 for
# closed window and for the duplicate race", "a section the student is not
# enrolled in refuses **404** with the same body a truly unknown section id
# gets", and "HTTP 503 with `Retry-After: 60`" for a provider that does not
# floor. 401 is `require_student`'s.
UNAUTHENTICATED_STATUS = 401
NOT_FOUND_STATUS = 404
CONFLICT_STATUS = 409
UNPROCESSABLE_STATUS = 422
CLASSIFIER_DOWN_STATUS = 503
RETRY_AFTER_SECONDS = "60"
BEARER_SCHEME = "Bearer"

# The status a failed CSRF check answers with, ruled in E2-08's security fix
# round and recorded in ADR 0114's status table. ADR 0089 settles the double-
# submit mechanism, the `X-Pulse-CSRF` header and the binding to `jti`, and
# settles no status — which is why the number belongs to a record of this
# ticket's rather than being inferred here. 403 rather than 401: the session is
# valid and the *request* is not, so a `WWW-Authenticate` challenge inviting the
# client to sign in again would be an instruction it cannot act on.
CSRF_REFUSED_STATUS = 403

# ADR 0089's two carriers for one session, named so a test can say which it
# means. "`session_from_request` reads the Bearer header before the cookie, so
# the Bearer path carries the session with no cookie required."
BEARER_SESSION = "bearer"
COOKIE_SESSION = "cookie"

# The header the double-submit token is echoed in, spelled by ADR 0089: the CSRF
# cookie "is not `HttpOnly` — the SPA echoes it in `X-Pulse-CSRF`". Transcribed
# from the record rather than chosen here, and it is the same string
# `tests/integration/test_lti_launch_door.py` quotes when it asserts that cookie
# is readable by a script.
CSRF_HEADER = "X-Pulse-CSRF"

# SPEC §3.3's own number for the prototype heuristic the fail-open floor keeps:
# "The prototype's ≥25-character heuristic is a placeholder only; production
# substantiveness is the classifier's call, with the character heuristic retained
# solely as the fail-open floor below." Transcribed from the section rather than
# read off `app.ai.tasks`, so a test about the floor's *verdict* is not agreeing
# with the implementation about where the floor sits.
CHARACTER_FLOOR = 25

# The bound a submitted comment is refused above, ruled in E2-08's security fix
# round: 4000 characters, checked at the edge before any provider call. A comment
# is free text with no length rule anywhere in SPEC §3.2, and an unbounded one is
# a request body that reaches the model — which is a bill, a latency and a prompt
# surface all at once.
COMMENT_MAXIMUM_LENGTH = 4000

# SPEC §10: "survey submit p95 < 2.5s including synchronous validity check". Not
# reconciled with §3.3's 2s classifier figure — that sentence says in as many
# words not to.
SUBMIT_BUDGET_SECONDS = 2.5

# ---------------------------------------------------------------------------
# The tables and columns E2-05 settled, and E2-08's two additions.
# ---------------------------------------------------------------------------

QUESTION_SET_TABLE = "question_set"
QUESTION_TABLE = "question"
RESPONSE_TABLE = "response"
ANSWER_TABLE = "answer"
CLASSIFICATION_TABLE = "classification"
SECTION_TABLE = "section"
WEEK_TABLE = "week"
TERM_TABLE = "term"
USER_TABLE = "user"
PLATFORM_TABLE = "lti_platform"
WINDOW_TABLE = "survey_window"

VERSION_COLUMN = "version"
POSITION_COLUMN = "position"
REQUIRED_IF_POSITION_COLUMN = "required_if_position"
REQUIRED_IF_AT_MOST_COLUMN = "required_if_at_most"
MINIMUM_VALUE_COLUMN = "minimum_value"
MAXIMUM_VALUE_COLUMN = "maximum_value"
STEP_COLUMN = "step"

RATING_COLUMN = "rating"
COMMENT_TEXT_COLUMN = "comment_text"
WORKLOAD_HOURS_COLUMN = "workload_hours"

# E2-08's own schema addition this file addresses rows by, settled by the work
# order: "`classification.answer_id` nullable FK RESTRICT to `answer` (ADR 0055's
# promised reference; a validity row written by this path always carries it)".
# `response.is_valid` is the other addition and is read by column name where it
# is asserted, because the assertion is about its value rather than about the
# spelling.
ANSWER_ID_COLUMN = "answer_id"

# The classification audit pair SPEC §7.4 requires of every row and ADR 0054
# fills with a description of the floor. The *values* are deliberately not named
# here: ADR 0054's own consequence is that the assertion is a **difference** —
# "it asserts a *difference* rather than these particular strings, so the shape is
# pinned and the spelling stays this record's to change".
PROMPT_VERSION_COLUMNS = ("prompt_version",)
MODEL_ID_COLUMNS = ("model_id", "model")

# ---------------------------------------------------------------------------
# The request body. **This is the one thing E2-08 does not settle** — see the
# module docstring. Two of the three names below are E2-05's own column names and
# the third is E2-05's ordinal; the envelope is this suite's choice, and a ruling
# is these four lines.
# ---------------------------------------------------------------------------

ANSWERS_KEY = "answers"
POSITION_KEY = "position"
SECTION_ID_KEY = "section_id"

# ---------------------------------------------------------------------------
# SPEC §3.2's five questions, as data.
# ---------------------------------------------------------------------------

INSTRUCTOR_RATING_POSITION = 1
INSTRUCTOR_COMMENT_POSITION = 2
COURSE_RATING_POSITION = 3
COURSE_COMMENT_POSITION = 4
WORKLOAD_POSITION = 5

# "Likert 1-5" and "range 0-40, 0.5-hour steps" (§3.2 writes both with an en
# dash; a hyphen is used here because the linter reads the en dash as a
# confusable, which is the convention `tests/integration/test_survey_schema.py`
# adopted for the same reason).
LIKERT_BOUNDS = (Decimal("1"), Decimal("5"), Decimal("1"))
WORKLOAD_BOUNDS = (Decimal("0"), Decimal("40"), Decimal("0.5"))

# "*Required if Q1 ≤ 2*" and "*Required if Q3 ≤ 2*".
REQUIRED_AT_MOST = 2

# How a question's shape is recognised, where the schema carries one. E2-05's
# `question` table may or may not type its three shapes as an enum — the ticket
# names the ordinal, the conditional rule and the bounds, and names no kind — so
# the column is *found* and its members are matched against these fragments. A
# column that is there and whose members none of these reaches stops the fixture
# with a message naming the interface question rather than seeding five questions
# of one shape, which is what the shared walker would do on its own (it fills an
# unnamed enum with the type's first member, so all five would be identical).
SHAPE_FRAGMENTS: dict[str, tuple[str, ...]] = {
    "rating": ("rating", "likert", "scale"),
    "comment": ("comment", "text", "free"),
    "workload": ("workload", "hours", "number", "numeric", "decimal"),
}
SHAPE_OF_POSITION = {
    INSTRUCTOR_RATING_POSITION: "rating",
    INSTRUCTOR_COMMENT_POSITION: "comment",
    COURSE_RATING_POSITION: "rating",
    COURSE_COMMENT_POSITION: "comment",
    WORKLOAD_POSITION: "workload",
}

# ---------------------------------------------------------------------------
# This suite's own values. None of them is a claim about anything the system
# decides.
# ---------------------------------------------------------------------------

# A platform registration these rows hang off. `https` and RFC 2606's `.invalid`
# because `committed_rows` opens a `Session` that states no environment, and
# Batch C's registration-address rules judge a session that states nothing as a
# deployment — deliberately, so a writer nobody thought about fails closed. A
# cleartext address here would be refused inside this fixture.
PLATFORM_ISSUER = "https://platform.e2-08-submit-path.invalid"
PLATFORM_CLIENT_ID = "e2-08-submit-path-client"
PLATFORM_JWKS_URL = "https://platform.e2-08-submit-path.invalid/.well-known/jwks.json"
PLATFORM_AUTHORIZATION_ENDPOINT = "https://platform.e2-08-submit-path.invalid/oidc/authorize"

# The cohorts the two sections are spelled as, so a section's code and its
# calendar agree the way `scripts/seed.py` writes them. Both are 12-week
# cohorts; `SEEDED_COHORTS` is transcribed from the seed in
# `tests/fixtures/survey_windows.py` and read rather than copied.
ENROLLED_COHORT = "U"
FOREIGN_COHORT = "R"

# An enrollment that contains every day any test here asks about, real or
# pretended. The window is the caller's business nowhere in this ticket — E1-13
# owns the boundary — so it is written wide on purpose and said so here.
ENROLLED_FROM = date(2020, 1, 1)

# A comment comfortably over the character floor (ADR 0054: the floor is the
# character heuristic at 25 characters or more, and it never answers `nonsense`),
# so a floored classification lands on `substantive` and the submission is valid.
# Every marked comment below is this sentence plus one of E2-07's in-band
# selectors, so the only difference between the taxonomy's rows is the selector.
SUBSTANTIVE_COMMENT = "the pacing in week 3 was too fast and the reading load doubled"


class SubmitContract(NamedTuple):
    """The names and statuses E2-08 settles, handed to a module rather than copied."""

    student_api_module: str
    validity_service_module: str
    copy_package: str
    submit_copy_module: str
    copy_entry_class: str
    copy_modules_function: str
    copy_mapping_name: str
    not_a_student_key: str
    classifier_down_key: str
    comment_already_judged_key: str
    unauthenticated: int
    csrf_refused: int
    not_found: int
    conflict: int
    unprocessable: int
    classifier_down: int
    retry_after_seconds: str
    submit_budget_seconds: float


@pytest.fixture
def submit_contract() -> SubmitContract:
    """See `SubmitContract`, and this module's docstring for what is not in it."""
    return SubmitContract(
        student_api_module=STUDENT_API_MODULE,
        validity_service_module=VALIDITY_SERVICE_MODULE,
        copy_package=COPY_PACKAGE,
        submit_copy_module=SUBMIT_COPY_MODULE,
        copy_entry_class=COPY_ENTRY_CLASS,
        copy_modules_function=COPY_MODULES_FUNCTION,
        copy_mapping_name=COPY_MAPPING_NAME,
        not_a_student_key=NOT_A_STUDENT_KEY,
        classifier_down_key=CLASSIFIER_DOWN_KEY,
        comment_already_judged_key=COMMENT_ALREADY_JUDGED_KEY,
        unauthenticated=UNAUTHENTICATED_STATUS,
        csrf_refused=CSRF_REFUSED_STATUS,
        not_found=NOT_FOUND_STATUS,
        conflict=CONFLICT_STATUS,
        unprocessable=UNPROCESSABLE_STATUS,
        classifier_down=CLASSIFIER_DOWN_STATUS,
        retry_after_seconds=RETRY_AFTER_SECONDS,
        submit_budget_seconds=SUBMIT_BUDGET_SECONDS,
    )


# ---------------------------------------------------------------------------
# Addresses nothing answers at.
# ---------------------------------------------------------------------------


def closed_loopback_address() -> str:
    """A loopback address whose port nothing is listening on.

    ADR 0056's `AIProviderUnreachableError` row is a connection that never
    reaches an endpoint, and E2-08's criterion 2 says in as many words that "a
    mock that answers cannot mint a connection that fails". A port bound and
    released is the cheapest thing that refuses immediately.
    """
    probe = socket.socket()
    try:
        probe.bind(("127.0.0.1", 0))
        port = int(probe.getsockname()[1])
    finally:
        probe.close()
    return f"127.0.0.1:{port}"


@pytest.fixture
def unreachable_ai_provider() -> str:
    """A `MOCK_AI_PROVIDER_BASE_URL` on a closed loopback port.

    See `closed_loopback_address` for why a released port rather than a mock. The
    variable is the mock triple's because a test process's `live=False` gateway
    reads that triple (the configuration split of 2026-09-02); what this fixture
    is *about* is unchanged — the application's own provider refusing a connection
    immediately.
    """
    return f"http://{closed_loopback_address()}/v1"


@pytest.fixture
def unreachable_broker() -> str:
    """A `REDIS_URL` on a closed loopback port, refusing immediately.

    The background `docs/MISTAKES.md` entry 41's near-miss is measured against:
    the broker is down, the refusal is instant, and anything slow about the
    request afterwards is the request's own doing.
    """
    return f"redis://{closed_loopback_address()}/0"


# ---------------------------------------------------------------------------
# The rows a submission needs, committed.
# ---------------------------------------------------------------------------


def shape_column(table: Any) -> tuple[str, dict[str, str]] | None:
    """`question`'s shape column and one member per §3.2 shape, or `None` if it has none.

    Found rather than named, for the reason this module's header gives: E2-05
    names the ordinal, the conditional rule and the bounds and names no kind, so
    a fixture that spelled one would be deciding a column E2-05 left open. Where
    the column is there, seeding five questions without naming it gives all five
    the enum's first member — the shared walker's rule — and a submission of five
    different shapes would then be refused inside this fixture.
    """
    candidates = [
        (column.name, list(getattr(column.type, "enums", ()) or []))
        for column in table.columns
        if isinstance(column.type, SqlEnum)
    ]
    typed = [(name, members) for name, members in candidates if members]
    if not typed:
        return None
    if len(typed) != 1:
        pytest.fail(
            f"`{QUESTION_TABLE}` carries {len(typed)} enumerated columns ({[n for n, _ in typed]}), "
            "so this fixture cannot tell which one says what kind of answer a question takes. "
            "`SHAPE_FRAGMENTS` in tests/fixtures/submit.py is where that is resolved."
        )
    name, members = typed[0]
    chosen: dict[str, str] = {}
    for shape, fragments in SHAPE_FRAGMENTS.items():
        matched = [
            member
            for member in members
            if any(fragment in member.lower() for fragment in fragments)
        ]
        if len(matched) != 1:
            pytest.fail(
                f"`{QUESTION_TABLE}.{name}` enumerates {members}, and {len(matched)} of them "
                f"reach the {shape!r} shape through {list(fragments)}. SPEC §3.2 has three answer "
                "shapes — a Likert rating, a free-text comment and a numeric workload — and this "
                "fixture has to seed one question of each. `SHAPE_FRAGMENTS` in "
                "tests/fixtures/submit.py is the one place that changes."
            )
        chosen[shape] = matched[0]
    return name, chosen


class SubmitWorld:
    """One section with an open window, its v1 question set, and a student enrolled in it.

    Committed throughout, because the application opens its own connection out of
    `DATABASE_URL` and sees nothing that has not been. Removed at teardown by
    `committed_rows`' diff, which also removes the rows the *submit path* wrote on
    its own connection — which is the whole reason these tests can read a response
    back at all.

    **Nothing here is a value a test then reads back as an answer**
    (`docs/MISTAKES.md` entry 30). The window instants are the caller's, the
    question bounds are SPEC §3.2's, and no `response`, `answer` or
    `classification` row is ever seeded: every one of those is written by the path
    under test.
    """

    def __init__(self, rows: Any, tables: dict[str, Any]) -> None:
        self.rows = rows
        self.tables = tables
        self.chain: dict[str, Any] = {}
        self.term: Any = None
        self.week: Any = None
        self.section: Any = None
        self.window: Any = None
        self.platform: Any = None
        self.student: Any = None
        self.question_set: Any = None
        self.questions: dict[int, Any] = {}

    # -- reaching a column ---------------------------------------------------

    def key_of(self, table_name: str) -> str:
        return single_primary_key(require_table(self.tables, table_name))

    def link(self, table_name: str, target: str) -> str:
        """The one column on `table_name` whose foreign key points at `target`."""
        table = require_table(self.tables, table_name)
        found = foreign_key_columns(table, target)
        if len(found) != 1:
            pytest.fail(
                f"`{table_name}` has {len(found)} foreign keys to `{target}` ({found}); this "
                "fixture needs exactly one to address the row it seeds."
            )
        return found[0]

    # -- building ------------------------------------------------------------

    def build(self, *, opens_at: datetime, closes_at: datetime) -> "SubmitWorld":
        """Seed the whole world, with the window the caller chose."""
        self.term = self.rows.seed(
            TERM_TABLE,
            self.chain,
            length_weeks=FALL_2026_TERM_WEEKS,
            start_date=FALL_2026_TERM_START,
            end_date=FALL_2026_TERM_END,
        )
        self.week = self.rows.seed(WEEK_TABLE, self.chain, number=1)
        self.section = self.seed_section(ENROLLED_COHORT)
        self.window = self.seed_window(self.section, opens_at=opens_at, closes_at=closes_at)
        self.platform = self.seed_platform()
        self.student = self.seed_student("e2-08-student")
        self.enrol(self.student, self.section)
        self.seed_question_set()
        self.rows.commit()
        return self

    def seed_section(self, cohort: str) -> Any:
        """One section of `cohort`, whose code and calendar agree the way the seed writes them."""
        length_weeks, _first_term_week, start = SEEDED_COHORTS[cohort]
        return self.rows.seed(
            SECTION_TABLE,
            self.chain,
            lms_section_code=f"{cohort}{COHORT_SECTION_ORDINAL}{COHORT_SECTION_MODALITY}",
            length_weeks=length_weeks,
            start_date=start,
            end_date=start + timedelta(days=length_weeks * 7 - 1),
        )

    def seed_window(self, section: Any, *, opens_at: datetime, closes_at: datetime) -> Any:
        """One `survey_window` over this term's week, with the instants the caller chose."""
        return self.rows.seed(
            WINDOW_TABLE,
            self.chain,
            section_id=section[self.key_of(SECTION_TABLE)],
            week_id=self.week[self.key_of(WEEK_TABLE)],
            term_id=self.term[self.key_of(TERM_TABLE)],
            opens_at=opens_at,
            closes_at=closes_at,
        )

    def seed_platform(self) -> Any:
        """The registration every seeded `user` belongs to. See `PLATFORM_ISSUER` for the `https`."""
        table = require_table(self.tables, PLATFORM_TABLE)
        return self.rows.seed(
            PLATFORM_TABLE,
            {},
            **{
                door_column_named(
                    table, PLATFORM_ISSUER_COLUMNS, "the issuer a session states"
                ): PLATFORM_ISSUER,
                door_column_named(
                    table, PLATFORM_CLIENT_ID_COLUMNS, "the tool this platform knows"
                ): PLATFORM_CLIENT_ID,
                door_column_named(
                    table, PLATFORM_JWKS_URL_COLUMNS, "where a verifying key set is fetched"
                ): PLATFORM_JWKS_URL,
                door_column_named(
                    table,
                    PLATFORM_AUTHORIZATION_ENDPOINT_COLUMNS,
                    "where a login initiation is sent (E1-05)",
                ): PLATFORM_AUTHORIZATION_ENDPOINT,
            },
        )

    def seed_student(self, subject: str) -> Any:
        """One `user` row for one subject at the seeded registration.

        The row a launch would have written. ADR 0028 gives a student no `person`
        row and no assignment — their access resolves from enrollment — so
        neither is written here.
        """
        return self.rows.seed(
            USER_TABLE,
            {},
            **{
                self.link(USER_TABLE, PLATFORM_TABLE): self.platform[self.key_of(PLATFORM_TABLE)],
                "lms_user_id": subject,
            },
        )

    def enrol(self, student: Any, section: Any) -> Any:
        """One live `enrollment` for this student in this section. See `ENROLLED_FROM`."""
        return self.rows.seed(
            "enrollment",
            {},
            **{
                self.link("enrollment", USER_TABLE): student[self.key_of(USER_TABLE)],
                self.link("enrollment", SECTION_TABLE): section[self.key_of(SECTION_TABLE)],
                "started_on": ENROLLED_FROM,
                "ended_on": None,
            },
        )

    def seed_question_set(self) -> None:
        """SPEC §3.2's five questions at version 1, with their rules carried as data."""
        table = require_table(self.tables, QUESTION_TABLE)
        found = shape_column(table)
        shape_name, members = found if found is not None else (None, {})

        self.question_set = self.rows.seed(QUESTION_SET_TABLE, {}, **{VERSION_COLUMN: 1})
        chain = {QUESTION_SET_TABLE: self.question_set}

        likert_minimum, likert_maximum, likert_step = LIKERT_BOUNDS
        workload_minimum, workload_maximum, workload_step = WORKLOAD_BOUNDS
        bounds_by_position = {
            INSTRUCTOR_RATING_POSITION: (likert_minimum, likert_maximum, likert_step),
            COURSE_RATING_POSITION: (likert_minimum, likert_maximum, likert_step),
            WORKLOAD_POSITION: (workload_minimum, workload_maximum, workload_step),
        }
        conditional_by_position = {
            INSTRUCTOR_COMMENT_POSITION: INSTRUCTOR_RATING_POSITION,
            COURSE_COMMENT_POSITION: COURSE_RATING_POSITION,
        }

        for position, shape in SHAPE_OF_POSITION.items():
            values: dict[str, Any] = {POSITION_COLUMN: position}
            if shape_name is not None:
                values[shape_name] = members[shape]
            bounds = bounds_by_position.get(position)
            if bounds is not None:
                values[MINIMUM_VALUE_COLUMN] = bounds[0]
                values[MAXIMUM_VALUE_COLUMN] = bounds[1]
                values[STEP_COLUMN] = bounds[2]
            conditional = conditional_by_position.get(position)
            if conditional is not None:
                values[REQUIRED_IF_POSITION_COLUMN] = conditional
                values[REQUIRED_IF_AT_MOST_COLUMN] = REQUIRED_AT_MOST
            self.questions[position] = self.rows.seed(QUESTION_TABLE, chain, **values)

    def close_the_window(self) -> None:
        """Move the seeded window's close into the past, and commit.

        The only way a suite can ask "what happens to a resubmission after the
        window closes" without waiting for one: the clock cannot be wound forward
        past a real instant, and moving the *window* changes the same comparison
        from the other side. E2-06's `open_window_for_section` answers from these
        rows, so a window whose `closes_at` has passed is a section with no open
        survey however the question is reached.
        """
        from sqlalchemy import update

        table = require_table(self.tables, WINDOW_TABLE)
        key = self.key_of(WINDOW_TABLE)
        now = datetime.now(UTC)
        self.rows.session.execute(
            update(table)
            .where(table.c[key] == self.window[key])
            .values(opens_at=now - timedelta(days=3), closes_at=now - timedelta(days=2))
        )
        self.rows.commit()

    def another_student(self, subject: str = "e2-08-second-student") -> Any:
        """A second student enrolled in the same section, committed."""
        student = self.seed_student(subject)
        self.enrol(student, self.section)
        self.rows.commit()
        return student

    def foreign_section(self) -> Any:
        """A second section, with its own open window, that the student is not enrolled in.

        Its window is seeded so that a refusal cannot be explained by the section
        having no open survey: the only difference from the student's own section
        is the enrollment.
        """
        section = self.seed_section(FOREIGN_COHORT)
        self.seed_window(
            section,
            opens_at=self.window["opens_at"],
            closes_at=self.window["closes_at"],
        )
        self.rows.commit()
        return section

    # -- reading back --------------------------------------------------------

    def rows_of(self, table_name: str, **matching: Any) -> list[dict[str, Any]]:
        """Every row of one table matching `matching`, read after ending this transaction.

        The transaction is ended first for the reason `WebIdentityRows.rows_of`
        gives: this connection has been open since it seeded, and what the submit
        path wrote was committed on another one, so a read inside the old
        snapshot reports "nothing happened" whatever happened.
        """
        from sqlalchemy import select

        table = require_table(self.tables, table_name)
        self.rows.session.rollback()
        statement = select(table)
        for column, value in matching.items():
            statement = statement.where(table.c[column] == value)
        return [dict(row) for row in self.rows.session.execute(statement).mappings()]

    def responses(self) -> list[dict[str, Any]]:
        """Every `response` row there is."""
        return self.rows_of(RESPONSE_TABLE)

    def answers_of(self, response: Mapping[str, Any]) -> list[dict[str, Any]]:
        """Every `answer` row of one response, in question order."""
        answers = self.rows_of(
            ANSWER_TABLE,
            **{self.link(ANSWER_TABLE, RESPONSE_TABLE): response[self.key_of(RESPONSE_TABLE)]},
        )
        question_key = self.link(ANSWER_TABLE, QUESTION_TABLE)
        position_of = {
            row[self.key_of(QUESTION_TABLE)]: row[POSITION_COLUMN]
            for row in self.questions.values()
        }
        return sorted(answers, key=lambda row: position_of.get(row[question_key], 0))

    def classifications_of(self, answer: Mapping[str, Any]) -> list[dict[str, Any]]:
        """Every `classification` row naming one answer (E2-08 adds the column)."""
        table = require_table(self.tables, CLASSIFICATION_TABLE)
        if ANSWER_ID_COLUMN not in table.c:
            pytest.fail(
                f"`{CLASSIFICATION_TABLE}` declares no `{ANSWER_ID_COLUMN}` (it declares "
                f"{[column.name for column in table.columns]}). E2-08's work order adds it as "
                "ADR 0055's promised reference — 'a validity row written by this path always "
                "carries it' — and without it a classification cannot be attributed to a comment."
            )
        return self.rows_of(
            CLASSIFICATION_TABLE, **{ANSWER_ID_COLUMN: answer[self.key_of(ANSWER_TABLE)]}
        )

    def audit_pair_of(self, classification: Mapping[str, Any]) -> tuple[Any, Any]:
        """The prompt version and model id of one classification row.

        Read through candidate lists rather than one spelling, because SPEC §7.4
        names "prompt version and model ID" in prose and E0-13 chose the columns.
        """
        table = require_table(self.tables, CLASSIFICATION_TABLE)
        prompt = door_column_named(table, PROMPT_VERSION_COLUMNS, "SPEC §7.4's prompt version")
        model = door_column_named(table, MODEL_ID_COLUMNS, "SPEC §7.4's model ID")
        return classification[prompt], classification[model]


@pytest.fixture
def submit_world(committed_rows: Any, metadata_tables: dict[str, Any]) -> SubmitWorld:
    """The world a submission needs, unbuilt — the caller chooses the window.

    Unbuilt, because which side of a window boundary the clock falls on is what
    three of E2-08's criteria are about, and a fixture that chose the instants
    would be answering them (`docs/MISTAKES.md` entry 30).
    """
    return SubmitWorld(committed_rows, metadata_tables)


@pytest.fixture
def open_now() -> tuple[datetime, datetime]:
    """A window that is open at the real clock's now, by a day on either side.

    A day rather than a minute so that nothing here can turn on the few seconds a
    container start costs, and so that a test whose subject is not the boundary
    never stands on one.
    """
    now = datetime.now(UTC)
    return now - timedelta(days=1), now + timedelta(days=1)


@pytest.fixture
def closed_already() -> tuple[datetime, datetime]:
    """A window that closed before the real clock's now. The other half of `open_now`."""
    now = datetime.now(UTC)
    return now - timedelta(days=3), now - timedelta(days=2)


# ---------------------------------------------------------------------------
# The tool, and a signed-in student.
# ---------------------------------------------------------------------------


@pytest.fixture
def open_submit_tool(
    tool_doors: Any,
    door_contract: Any,
    configured_env: dict[str, str],
    unreachable_broker: str,
) -> Callable[..., Any]:
    """Build the tool with the AI provider and broker a test chose.

    Every variable this sets is one some test here depends on, and each is stated
    rather than inherited (`docs/MISTAKES.md` entry 40): the environment, because
    the E2-04 clock override applies in `development` and nowhere else (ADR
    0109); the institution timezone, because SPEC §3.1 puts every window at a
    wall-clock time in it; the provider address, because ADR 0056's taxonomy is
    what criterion 2 walks; and the broker, because entry 41's near-miss is about
    what a request does when it is down.
    """

    def open_it(*, ai_base_url: str, redis_url: str | None = None, **extra: str) -> Any:
        values = {
            door_contract.settings["public_base_url"]: door_contract.public_base_url,
            ENVIRONMENT_VARIABLE: DEVELOPMENT,
            INSTITUTION_TIMEZONE_VARIABLE: INSTITUTION_TIMEZONE,
            MOCK_AI_PROVIDER_BASE_URL_VARIABLE: ai_base_url,
            REDIS_URL_VARIABLE: unreachable_broker if redis_url is None else redis_url,
            **extra,
        }
        return tool_doors(values, {})

    return open_it


def session_secret(configured: Mapping[str, str]) -> bytes:
    """The secret the application signs and verifies a session with, as `bytes`.

    Read out of the documented mapping the application was built from rather than
    out of `os.environ`, so the token this suite mints and the token the
    application verifies cannot come from two different readings of the
    environment. E1-08's interface ruling makes the parameter `bytes`.
    """
    value = configured.get("SESSION_SECRET")
    if not value:
        pytest.fail(
            "`SESSION_SECRET` is not among the documented variables `configured_env` lays down "
            f"(it lays down {sorted(configured)}). E1-08 signs every session with it, so without "
            "it there is no student to submit as."
        )
    return value.encode("utf-8")


def issue_student_session(
    *, secret: bytes, issuer: str, subject: str, user_id: Any, role_name: str = "STUDENT"
) -> str:
    """One session token for a student, minted through the module both doors mint through.

    **Minted rather than launched**, because what a launch resolves is E1-10's
    and E1-13's subject and this ticket's is what a signed-in student may write.
    Driving a whole LTI launch to obtain a token would make every test here rest
    on the launch door as well, and a red would name the wrong ticket.

    `person_id` and `user_id` are E1-12's additions to `SessionClaims`, and they
    are bound **by signature** rather than passed blind: a parameter this cannot
    fill stops with a message naming it, which is an interface question for the
    ticket rather than something to guess at (the device
    `tests/fixtures/ai_tasks.py` uses for the same reason).
    """
    import inspect

    import app.services.session as session_module
    from app.services.authz import Door, LandingRole

    issue = getattr(session_module, "issue_session", None)
    if not callable(issue):
        pytest.fail(
            "`app.services.session` exposes no `issue_session`. E1-08 puts the shared session "
            "module there and both doors issue through it."
        )
    role = getattr(LandingRole, role_name, None)
    if role is None:
        pytest.fail(
            f"`LandingRole` has no member {role_name!r}; it has "
            f"{sorted(member.name for member in LandingRole)}. E1-13 moves the enum into "
            "`app.services.authz` with its member names unchanged."
        )
    parameters = inspect.signature(issue).parameters
    values: dict[str, Any] = {
        "door": Door.LAUNCH,
        "role": role,
        "sub": subject,
        "iss": issuer,
        "secret": secret,
    }
    if "user_id" not in parameters:
        pytest.fail(
            "`issue_session` takes no `user_id` — it takes "
            f"{sorted(parameters)}. E1-12 adds `user_id` to `SessionClaims` as 'the launch-side "
            "row', and E2-08's work order makes `require_student` hand those claims to the submit "
            "path, which writes `response.user_id` from them. Without it there is no student for "
            "a submission to belong to. It is declared `str | None`, because a session is a JWT "
            "and a claim in one is JSON."
        )
    # **`str(...)` and not the raw column value.** `user.id` is a `uuid.UUID`
    # coming out of the database (ADR 0016), `issue_session` declares
    # `user_id: str | None`, and the claim goes into a JWT payload — so handing
    # the uuid straight through dies in `json.dumps` with "Object of type UUID is
    # not JSON serializable", inside the fixture, before any request is made.
    # That is `docs/MISTAKES.md` entry 13's closing sentence: when a test fails
    # inside its own fixture, suspect the fixture first. It is coerced here, at
    # the one point the value enters the session machinery, rather than at each
    # call site.
    values["user_id"] = str(user_id)
    return issue(**values)


def session_cookie_names() -> tuple[str, str]:
    """`SESSION_COOKIE` and `CSRF_COOKIE`, read out of the module both doors issue through.

    Imported rather than spelled, the way `tests/integration/test_web_login_door.py`
    and `test_landing_resolves_from_assignments.py` already read them: E1-08 owns
    the two names and a copy here would be a fourth place for them to drift.
    """
    try:
        from app.services.session import CSRF_COOKIE, SESSION_COOKIE
    except ImportError as missing:  # pragma: no cover - a red, not a branch
        pytest.fail(
            f"`app.services.session` does not export the cookie names ({missing}). E1-08's module "
            "layout puts `SESSION_COOKIE`/`CSRF_COOKIE` there and both doors set them."
        )
    return SESSION_COOKIE, CSRF_COOKIE


def csrf_token_for(session_token: str, secret: bytes) -> str:
    """The double-submit token ADR 0089 binds to one session's `jti`.

    > CSRF, live because of `SameSite=None`: a double-submit token bound to the
    > session's `jti` by HMAC (`issue_csrf_token`/`verify_csrf_token`). A tossed
    > cookie without the secret still fails, and a token minted for one session
    > does not verify against another's `jti`.

    So the token is *minted through the tool's own primitive* rather than composed
    here. A fixture that built the HMAC itself would be a second implementation
    for the check to agree with (`docs/MISTAKES.md` entry 19), and it would go on
    passing if the binding to `jti` were dropped — which is half of what the
    primitive is for.

    The `jti` comes back from `verified_session`, and the parameters are bound by
    name for the reason `issue_student_session` binds its own that way: E1-08's
    interface ruling names the two functions and spells no signature, so a
    parameter this cannot fill stops with a message naming it rather than being
    guessed at.
    """
    import inspect

    import app.services.session as session_module

    issue = getattr(session_module, "issue_csrf_token", None)
    if not callable(issue):
        pytest.fail(
            "`app.services.session` exposes no `issue_csrf_token`; it exposes "
            f"{sorted(n for n in vars(session_module) if not n.startswith('_'))}. ADR 0089 names "
            "`issue_csrf_token`/`verify_csrf_token` as the double-submit pair, and E2's first "
            "mutating endpoint is what consumes the check."
        )
    claims = session_module.verified_session(session_token, secret)
    if claims is None:
        pytest.fail(
            "`verified_session` refused the token this suite minted, so there is no `jti` to bind "
            "a CSRF token to. `test_the_minted_session_verifies_as_the_seeded_student` is where "
            "that is diagnosed."
        )

    available = {"jti": claims.jti, "secret": secret}
    aliases = {"jti": ("jti", "session_jti", "sid", "session_id"), "secret": ("secret", "key")}
    values: dict[str, Any] = {}
    for parameter in inspect.signature(issue).parameters.values():
        if parameter.kind in (parameter.VAR_POSITIONAL, parameter.VAR_KEYWORD):
            continue
        role = next(
            (name for name, names in aliases.items() if parameter.name in names),
            None,
        )
        if role is None:
            if parameter.default is not parameter.empty:
                continue
            pytest.fail(
                f"`issue_csrf_token` requires a parameter `{parameter.name}` this fixture has "
                f"nothing to fill from; it is offering {sorted(available)}. ADR 0089 makes the "
                "token 'bound to the session's `jti` by HMAC', so those two are what a mint "
                "should need — a third required input is an interface question for the ticket."
            )
        else:
            values[parameter.name] = available[role]
    return str(issue(**values))


class SignedInStudent:
    """A student, the tool they submit through, and the world they submit into."""

    def __init__(self, client: Any, world: SubmitWorld, token: str, secret: bytes) -> None:
        self.client = client
        self.world = world
        self.token = token
        self.secret = secret

    @property
    def authorization(self) -> dict[str, str]:
        """The Bearer header a submission carries by default.

        Bearer and not the session cookie for most of this suite, and the work
        order is why: an absent or invalid session is refused with
        `WWW-Authenticate: Bearer`, which is a statement about the scheme this
        API is presented a session under. ADR 0089 makes it the path the SPA
        actually uses — "the SPA captures the fragment into `sessionStorage` …
        and sends it as `Authorization: Bearer` thereafter" — and
        `session_from_request` "reads the Bearer header before the cookie".

        The cookie path is reachable through `submit(via=COOKIE_SESSION)`, and it
        is the one E1-08's CSRF pair guards.
        """
        return {"authorization": f"{BEARER_SCHEME} {self.token}"}

    def submit(
        self,
        answers: Mapping[int, Any],
        *,
        section: Any = None,
        authenticated: bool = True,
        via: str = BEARER_SESSION,
        csrf: bool = True,
        csrf_token: str | None = None,
    ) -> Any:
        """Post one submission and answer the response, whatever its status.

        `via` decides which of ADR 0089's two carriers the session rides, and
        `csrf` whether the double-submit pair goes with it. The two are separate
        arguments because the exemption is a property of the *carrier*: a Bearer
        header is not sent by a cross-site form, so a request that carries one
        is not a request a browser can be tricked into making, and the check has
        nothing to protect there.

        **`csrf_token` puts a chosen value in both the cookie and the header**,
        which is the only shape that can tell verification from a comparison. An
        attacker who can make a browser send a cross-site request can also toss a
        cookie, so they control both halves of a double submit; a check that
        compares the two to each other passes for them. Only ADR 0089's HMAC
        against *this* session's `jti` refuses it. Handing the value to both is
        therefore not a convenience — a helper that set only the header would be
        caught by a comparison, and the test would pass against a control that
        does not hold (`docs/disputes/E2-08-06.md`, mutation M1c).
        """
        target = self.world.section if section is None else section
        section_id = target[self.world.key_of(SECTION_TABLE)]
        template = submit_route(self.client)
        url, body = submission_request(template, section_id, answers, self.world)

        headers: dict[str, str] = {}
        cookies: dict[str, str] = {}
        if authenticated and via == BEARER_SESSION:
            headers.update(self.authorization)
        elif authenticated and via == COOKIE_SESSION:
            session_cookie, csrf_cookie = session_cookie_names()
            cookies[session_cookie] = self.token
            if csrf_token is not None:
                cookies[csrf_cookie] = csrf_token
                headers[CSRF_HEADER] = csrf_token
            elif csrf:
                minted = csrf_token_for(self.token, self.secret)
                cookies[csrf_cookie] = minted
                headers[CSRF_HEADER] = minted
        elif authenticated:
            pytest.fail(
                f"`submit(via={via!r})` names no carrier this fixture knows. ADR 0089 gives a "
                f"session two: {BEARER_SESSION!r} and {COOKIE_SESSION!r}."
            )

        # Set on the client and cleared afterwards rather than passed per
        # request: httpx deprecates a per-request `cookies` argument, and
        # `filterwarnings = ["error::DeprecationWarning"]` in `pyproject.toml`
        # turns a deprecation into a failed test. Cleared in a `finally` so a
        # cookie set for one request cannot authenticate the next one — which is
        # exactly the near miss the Bearer exemption test would otherwise pass on.
        self.client.cookies.clear()
        try:
            for name, value in cookies.items():
                self.client.cookies.set(name, value)
            return self.client.post(url, json=body, headers=headers)
        finally:
            self.client.cookies.clear()

    def submit_timed(self, answers: Mapping[int, Any], **kwargs: Any) -> tuple[Any, float]:
        """The same submission, with the wall-clock seconds it took."""
        started = time.perf_counter()
        answered = self.submit(answers, **kwargs)
        return answered, time.perf_counter() - started


def submit_route(client: Any) -> str:
    """The path template of the one `POST` route `app.api.student` defines.

    **Discovered, not named.** E2-08's work order settles the module — "the submit
    route goes in a new file `backend/app/api/student.py`" — and settles no URL,
    so the module is the fact this reads and the path is whatever the ticket's
    author registered it at. A constant here would be this suite choosing an
    address the ticket left open.

    **The walk is `fixtures.routing.every_route`, and this file no longer has one
    of its own.** On the pinned `fastapi` 0.141.1, `include_router` appends a
    single `_IncludedRouter` carrying no `path`, no `methods` and no `endpoint`,
    so a walk over `application.routes` sees only what the factory registered
    directly — FastAPI's four documentation paths and nothing else. Written that
    way, this helper answered "`app.api.student` defines 0 POST routes" with the
    route built and with it absent alike, so it discriminated nothing about this
    ticket (`docs/MISTAKES.md` entry 24). That reading was ruled on in
    `docs/disputes/E2-04-01.md`, and the ruling required one shared helper rather
    than a repair per caller; this was the third walk written the blind way, and
    `docs/disputes/E2-08-01.md` is where it was caught. `docs/MISTAKES.md` entry
    13 is the rule — one helper, reached from every place that asks the question.

    **The flattening does not widen what is asserted.** An application whose
    routers were never registered appends no `_IncludedRouter` to recurse into,
    so the near miss this exists to catch — a module that defines a route nothing
    registers — fails here exactly as before.
    """
    routes = [
        route
        for route in every_route(client.app)
        if "POST" in (getattr(route, "methods", None) or set())
        and getattr(getattr(route, "endpoint", None), "__module__", None) == STUDENT_API_MODULE
    ]
    if len(routes) != 1:
        registered = sorted(
            f"{sorted(getattr(route, 'methods', None) or [])} {getattr(route, 'path', '?')} "
            f"({getattr(getattr(route, 'endpoint', None), '__module__', '?')})"
            for route in every_route(client.app)
        )
        pytest.fail(
            f"`{STUDENT_API_MODULE}` defines {len(routes)} POST routes on the built application; "
            "E2-08 ships exactly one, the submit route. The application registers: "
            f"{registered}. The module is the work order's ('the submit route goes in a new file "
            "`backend/app/api/student.py`'), and the router has to be registered in "
            "`app.main.create_app` for a request to reach it at all."
        )
    return str(routes[0].path)


def submission_request(
    template: str,
    section_id: Any,
    answers: Mapping[int, Any],
    world: SubmitWorld,
) -> tuple[str, dict[str, Any]]:
    """The URL and JSON body of one submission. See this module's docstring.

    The section travels in the path where the route declares a parameter for it
    and in the body where it declares none — both are reasonable spellings and
    E2-08 settles neither, so tolerating the two is what keeps a stylistic choice
    from reddening every test in this ticket.
    """
    parameters = re.findall(r"\{([^}/]+)\}", template)
    body: dict[str, Any] = {ANSWERS_KEY: submission_answers(answers, world)}
    if len(parameters) == 1:
        return template.replace("{" + parameters[0] + "}", str(section_id)), body
    if not parameters:
        body[SECTION_ID_KEY] = str(section_id)
        return template, body
    pytest.fail(
        f"The submit route's path is {template!r}, which declares {len(parameters)} parameters "
        f"({parameters}). A submission names one section, so this fixture can fill one path "
        "parameter or none; `submission_request` in tests/fixtures/submit.py is where a third "
        "spelling would be taught."
    )


def submission_answers(answers: Mapping[int, Any], world: SubmitWorld) -> list[dict[str, Any]]:
    """§3.2's answers as the body carries them, keyed by position and by value column.

    A value of `None` is an omitted answer and is left out of the body entirely —
    which is what "the comment is blank" and "the required comment is missing"
    both look like on the wire, and the difference between them is the Likert
    beside it rather than the shape of the request.
    """
    built: list[dict[str, Any]] = []
    for position, value in sorted(answers.items()):
        if value is None:
            continue
        shape = SHAPE_OF_POSITION[position]
        key = {
            "rating": RATING_COLUMN,
            "comment": COMMENT_TEXT_COLUMN,
            "workload": WORKLOAD_HOURS_COLUMN,
        }[shape]
        built.append({POSITION_KEY: position, key: value})
    return built


def a_valid_submission(*, comment: str | None, instructor_rating: int = 4) -> dict[int, Any]:
    """The five answers of an ordinary submission, with the comment the caller chose.

    `comment=None` is a submission that carries no instructor comment at all,
    which is legal at any Likert above §3.2's threshold and is how ADR 0115's
    withdrawal is posed: a question answered before and not now.

    The instructor rating defaults to 4, which is above §3.2's "Required if Q1 ≤ 2"
    threshold, so the comment beside it is *optional* — a test about a bounce is
    then unambiguously about the classifier's verdict rather than about a required
    field. The course comment is left blank for the same reason: exactly one
    comment is submitted, so exactly one classification is expected.
    """
    return {
        INSTRUCTOR_RATING_POSITION: instructor_rating,
        INSTRUCTOR_COMMENT_POSITION: comment,
        COURSE_RATING_POSITION: 5,
        COURSE_COMMENT_POSITION: None,
        WORKLOAD_POSITION: 6.5,
    }


@pytest.fixture
def signed_in_student(
    configured_env: dict[str, str],
) -> Callable[[Any, SubmitWorld], SignedInStudent]:
    """A student signed in at the tool, for the world that was just built."""

    def sign_in(
        client: Any, world: SubmitWorld, student: Any = None, *, role_name: str = "STUDENT"
    ) -> SignedInStudent:
        row = world.student if student is None else student
        secret = session_secret(configured_env)
        token = issue_student_session(
            secret=secret,
            issuer=PLATFORM_ISSUER,
            subject=row["lms_user_id"],
            user_id=row[world.key_of(USER_TABLE)],
            role_name=role_name,
        )
        return SignedInStudent(client, world, token, secret)

    return sign_in


# ---------------------------------------------------------------------------
# Reading what a refusal served.
# ---------------------------------------------------------------------------


def served_text(response: Any) -> str:
    """Every string a JSON response body carries, joined, or its raw text.

    A refusal's copy may sit under `detail`, inside a list of errors, or beside a
    key. What every test here asks is whether the registry's string *reached the
    student*, so the body is flattened once, here, rather than each module
    guessing at the envelope FastAPI produced.
    """
    try:
        document = response.json()
    except ValueError:
        return response.text

    collected: list[str] = []

    def walk(value: Any) -> None:
        if isinstance(value, str):
            collected.append(value)
        elif isinstance(value, Mapping):
            for member in value.values():
                walk(member)
        elif isinstance(value, list | tuple):
            for member in value:
                walk(member)

    walk(document)
    return "\n".join(collected)


def copy_texts() -> dict[str, str]:
    """Every string the copy registry publishes, keyed by its dotted key.

    The one reader for "is this string externalized", so the route-side tests and
    the registry-side tests cannot come to disagree about where the registry is
    (`docs/MISTAKES.md` entry 13).
    """
    import importlib

    try:
        package = importlib.import_module(COPY_PACKAGE)
    except ModuleNotFoundError as missing:  # pragma: no cover - a red, not a branch
        pytest.fail(
            f"`{COPY_PACKAGE}` does not import ({missing}). E2-08 establishes the copy registry "
            "there, and every refusal this path serves is required to be one of its strings."
        )
    modules_function = getattr(package, COPY_MODULES_FUNCTION, None)
    if not callable(modules_function):
        pytest.fail(
            f"`{COPY_PACKAGE}` exposes no callable `{COPY_MODULES_FUNCTION}`. E2-08's work order "
            "establishes the registry as a package whose modules are enumerated rather than "
            "listed, because a guard's inventory must not be shrinkable by an edit to the thing "
            "it guards."
        )
    texts: dict[str, str] = {}
    for module in modules_function():
        mapping = getattr(module, COPY_MAPPING_NAME, None)
        if not isinstance(mapping, Mapping):
            pytest.fail(
                f"`{getattr(module, '__name__', module)}` publishes no `{COPY_MAPPING_NAME}` "
                "mapping. Each surface adds one module defining "
                f"`{COPY_MAPPING_NAME}: Mapping[str, CopyEntry]` keyed by dotted keys."
            )
        for key, entry in mapping.items():
            texts[str(key)] = str(getattr(entry, "text", entry))
    if not texts:
        pytest.fail(
            f"`{COPY_PACKAGE}.{COPY_MODULES_FUNCTION}()` published no strings at all, so every "
            "assertion that a served string is externalized would be satisfied by a registry "
            "with nothing in it (`docs/MISTAKES.md` entry 3)."
        )
    return texts


def externalized_key_for(response: Any) -> str:
    """The registry key whose text the response served, or a failure saying it served none.

    Criterion 4 turned into a question a test can ask: "Every user-facing string
    this path serves is externalized where E2-11's inventory will read it." A
    refusal whose sentence is written inline in the route passes no assertion
    here.
    """
    body = served_text(response)
    matched = sorted(key for key, text in copy_texts().items() if text and text in body)
    if len(matched) != 1:
        pytest.fail(
            f"The response served {body[:400]!r}, and {len(matched)} of the copy registry's "
            f"strings appear in it ({matched}). E2-08's fourth criterion: every user-facing "
            "string this path serves is externalized where E2-11's inventory will read it, and "
            "routes serve copy only by key lookup rather than as an inline sentence."
        )
    return matched[0]


@pytest.fixture
def registry_key_of() -> Callable[[Any], str]:
    """Hand `externalized_key_for` to a test, so the reading is done in one place."""
    return externalized_key_for


@pytest.fixture
def registry_texts() -> Callable[[], dict[str, str]]:
    """Hand `copy_texts` to a test."""
    return copy_texts


# ---------------------------------------------------------------------------
# The re-classification the request enqueues, reached without naming it.
# ---------------------------------------------------------------------------

# How the async re-classification is recognised. E2-08's work order settles that
# it is "a Celery task in `backend/app/jobs/tasks.py` (thin wrapper pattern)
# calling into `services/validity.py`" and settles no name, so it is matched by a
# word from what it does — the same device `tests/fixtures/ai_tasks.py` uses, and
# for the same reason: pinning a name here would make the implementer build to
# this fixture instead of to the ticket.
RECLASSIFY_FRAGMENTS = ("reclassif", "re_classif", "classif", "validity")

# A task the walk below must find, whatever else it finds — the control that
# makes "found nothing" mean something. `ping` has been a `@celery_app.task` in
# `app.jobs.tasks` since E0-03 and `tests/unit/test_celery_app.py` asserts it is
# one, so a walk that cannot see it is broken rather than looking at a module
# that has lost its deliverable. If `ping` is ever renamed, this constant is the
# one line that changes and the test that pins it is the one to read first.
CERTAINLY_PRESENT_TASK = "ping"


def reclassification_entry_point(module: Any) -> Any:
    """The one member of `app.jobs.tasks` that re-runs a floored classification.

    Matched over *every* public member rather than over plain functions, because a
    Celery task is an object rather than a function and a walk that looked only
    for functions would find nothing and report the deliverable missing when it
    is there.

    **The module filter asks the task's `run`, not the task.** `@celery_app.task`
    on an unfinalized app hands back a `celery.local.PromiseProxy`, and
    `__module__` is an attribute of the *class*, so the lookup finds
    `PromiseProxy`'s own — `'celery.local'` — and never reaches the proxy's
    `__getattr__`. Asked of the proxy, this filter excluded every task the module
    has ever defined, `ping` included, and then reported the deliverable missing
    over an empty candidate list: a discovery that could never find anything,
    which is what `docs/MISTAKES.md` entry 35 exists for. `docs/disputes/
    E2-08-02.md` carries the measurement. The filter's purpose is unchanged — it
    keeps the *imported* service functions (`sync_all_rosters`,
    `derive_windows_for_all_sections`) out of the match, so a wrapper and the
    function it wraps do not compete — and `run.__module__` is the value that
    answers that question correctly.

    **The walk is made to find a task that is certainly there, before it reports
    that one is not.** That is `docs/MISTAKES.md` entry 35's rule and it is the
    repair the `celery.local` defect did not get: a filter that excluded every
    task in the module reported the deliverable missing, in the same words it
    would have used had the deliverable really been missing, and nothing in the
    message could tell the two apart. `ping` is the control because it is the one
    task in this module that no ticket owns and none will remove — E0-03 shipped
    it to prove the round trip. A guard that only ever reports absence cannot say
    which mechanisms it can see; this one has to see one first.
    """
    candidates = {
        name: value
        for name, value in vars(module).items()
        if not name.startswith("_")
        and callable(getattr(value, "run", value))
        and getattr(getattr(value, "run", value), "__module__", "") == module.__name__
    }
    if CERTAINLY_PRESENT_TASK not in candidates:
        pytest.fail(
            f"This walk over `app.jobs.tasks` cannot see `{CERTAINLY_PRESENT_TASK}`, which E0-03 "
            f"shipped and `tests/unit/test_celery_app.py` asserts is a Celery task there. It sees "
            f"{sorted(candidates)}, out of a module holding "
            f"{sorted(name for name in vars(module) if not name.startswith('_'))}.\n\n"
            "**So this is a defect in `reclassification_entry_point`, not in E2-08's async "
            "re-classification.** Read it that way before reading anything else: the walk is "
            "blind, and whatever it goes on to say about the re-classification being present or "
            "absent is a statement it is not in a position to make. `docs/disputes/E2-08-02.md` "
            "is the last time this happened — a Celery task proxy reports `celery.local` as its "
            "`__module__`, so a filter asking the proxy rather than its `run` excluded every task "
            "the module has ever defined. This control exists so that the next such filter fails "
            "here, naming itself, rather than three lines further down naming somebody's ticket."
        )
    for fragment in RECLASSIFY_FRAGMENTS:
        matched = {name: value for name, value in candidates.items() if fragment in name.lower()}
        if len(matched) == 1:
            return next(iter(matched.values()))
        if len(matched) > 1:
            pytest.fail(
                f"`app.jobs.tasks` defines {len(matched)} members whose name carries "
                f"{fragment!r} ({sorted(matched)}), so this cannot tell which one is the async "
                "re-classification. `RECLASSIFY_FRAGMENTS` in tests/fixtures/submit.py is the "
                "one line that changes."
            )
    pytest.fail(
        f"`app.jobs.tasks` defines no member whose name carries any of "
        f"{list(RECLASSIFY_FRAGMENTS)} — it defines {sorted(candidates)}. E2-08's scope names the "
        "async re-classification twice: 'enqueues the async re-classification' and 'a beat "
        "schedule entry ... sweeping unresolved floored classifications'."
    )


def run_reclassification(module: Any) -> Any:
    """Run the re-classification once, in this process, filling nothing it did not ask for.

    A sweep of unresolved floored classifications takes no subject, so the
    expected shape is a call with no arguments. A parameter this cannot fill
    stops with a message naming it rather than being guessed at.
    """
    import inspect

    task = reclassification_entry_point(module)
    runner = getattr(task, "run", task)
    required = [
        parameter
        for parameter in inspect.signature(runner).parameters.values()
        if parameter.default is parameter.empty
        and parameter.kind not in (parameter.VAR_POSITIONAL, parameter.VAR_KEYWORD)
    ]
    if required:
        pytest.fail(
            f"The re-classification entry point requires {[p.name for p in required]}, and this "
            "fixture has nothing to fill them from. E2-08's work order makes it a sweep of "
            "unresolved floored classifications, which names no subject; if it takes one, "
            "`run_reclassification` in tests/fixtures/submit.py is where that is taught."
        )
    return runner()


@pytest.fixture
def reclassify() -> Callable[[Any], Any]:
    """Hand `run_reclassification` to a test. See it for what it refuses to guess."""
    return run_reclassification
