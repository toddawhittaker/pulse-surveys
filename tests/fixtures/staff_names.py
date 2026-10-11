"""E7-01 — the staff-name channel, the two response records, and the world they are read over.

Six test modules ask the same channel the same questions, so the driving lives
here and each module asserts (`docs/MISTAKES.md` entry 13). Nothing in this
repository answers any of it yet.

**The names E7-01's work order settles, transcribed once** (decisions 1 to 4, and
the two rulings appended to it after the first pass, on B1 and B2):

  - the definer `public.section_staff_names(p_section_id uuid, p_reader_user_id
    uuid, p_reader_person_id uuid) RETURNS TABLE (person_id uuid, display_name
    text)`, owned by the NOLOGIN role `pulse_staff_name_definer`. Exactly one
    reader key is non-null, else zero rows; a student is asked about by user key
    (a launched student has no `person`, ADR 0028), a member of staff by person key;
  - the one Python door `app.services.response_loop.section_staff_names(session,
    *, section_id, reader_person_id) -> list[StaffName]`, asked here about staff
    readers only (the B1 ruling does not say how it takes a user key);
  - the survey payload's section entry member `instructors: list[str]`, the
    section's live teaching instructors only;
  - the tables `instructor_response` and `response_policy`, every column of each
    and the ones `pulse_app` inserts (the B2 ruling), their vocabularies, and the
    text bound `RESPONSE_TEXT_MAX = 4000`.

**What is still not settled.** `StaffName`'s members: the name is read off
`display_name`, the definer's own result column, and a `StaffName` that calls it
something else fails naming the work order rather than being guessed at.

**The world** is E6-05's lead-review world (`tests/fixtures/lead_review.py`): one
department holding the own course (sections `F1WW`, taught by the door's
instructor, and `Q1WW`), a sibling course (cohort `Y`, its own lead) and an
unmapped course (cohort `4`, no lead, so it falls to the chair). Added here:

  - a distinctive `person.identity_name` on every staff member, so a name found in
    an answer can be attributed to exactly one person;
  - an instructor on `Q1WW`, on the sibling course's section and on the unmapped
    course's section, so each passing twin has a name to answer with;
  - a chair of a **second** department under the same college, the one-level-out
    chair (`docs/MISTAKES.md` entry 53).

Students (a `user` and an enrollment, no `person`, as a launch leaves them), a
former teacher whose grant the roster ended, a two-hat person and a published
response are planted by methods a test calls, so each test's own body
says which of them its world holds.

**The clock.** The report world pretends a fixed 2026 instant. Whether a live
enrollment is judged against that pretended clock or against the database's own
date is the implementer's (`survey_read._live_enrollments` reads one, a SQL body
may read the other), so this world moves the development clock to the real
present before anything is planted, and every enrollment date is counted from the
real today. Both readings then agree on which enrollment is live, and a red cannot
be a calendar accident (the E2E world-building trap of the same shape).

**Every read is made on `pulse_app`'s own connection** (`application_session`),
never on the superuser that seeds (`docs/MISTAKES.md` entry 46). Every guard on a
deliverable is a plain function called from a test body, so an unbuilt tree is a
FAILED naming it, never an ERROR in setup (`docs/MISTAKES.md` entry 44).

**Nothing here decides an answer.** It plants, names, calls and reads back; every
expectation is written out in the test that makes it (`docs/MISTAKES.md` entries
19 and 30).
"""

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from importlib import import_module
from typing import Any, NamedTuple
from uuid import uuid4

import pytest

from fixtures.landing import EnrollmentRows
from fixtures.lead_review import (
    CHAIR_ROLE,
    COLLEGE_TABLE,
    SIBLING_COHORT,
    UNMAPPED_COHORT,
    LeadReviewWorld,
)
from fixtures.report_api import INSTRUCTOR_ROLE, TAUGHT_COHORT, UNTAUGHT_COHORT
from fixtures.roster_sync import (
    END_TEACHING_INSTRUCTOR_CALL,
    ended_teaching_grants,
    institution_today,
    require_the_ended_teaching_grant_table,
    require_the_grant_ending_definer,
)
from fixtures.supervision import foreign_key_columns, require_table, single_primary_key

# ---------------------------------------------------------------------------
# The names E7-01's work order settles, spelled once.
# ---------------------------------------------------------------------------

# Decision 1, as the ruling on B1 amends it: the definer, its owner, and how it is
# called. Three parameters — the section, the reader's `user` key and the reader's
# `person` key. Exactly one reader key is non-null, or the answer is zero rows. The
# student check runs on the user key (a launched student has no `person`, ADR
# 0028); the teaching and lead/chair checks run on the person key.
DEFINER = "section_staff_names"
DEFINER_SIGNATURE = "public.section_staff_names(uuid,uuid,uuid)"
DEFINER_ROLE = "pulse_staff_name_definer"
# Cast, never `::`: SQLAlchemy's `text()` stops reading a bind parameter when a
# colon follows it (`tests/fixtures/roster_sync.py::END_TEACHING_INSTRUCTOR_CALL`),
# and an uncast NULL is untyped.
DEFINER_CALL = (
    "SELECT * FROM public.section_staff_names("
    "CAST(:section_id AS uuid), CAST(:reader_user_id AS uuid), "
    "CAST(:reader_person_id AS uuid))"
)
# Decision 1 and 2: the result is exactly these two columns, in this order.
DEFINER_COLUMNS = ("person_id", "display_name")
DEFINER_RESULT = "TABLE(person_id uuid, display_name text)"

# Decision 3: the one Python door and its keyword parameters.
SERVICE_MODULE = "app.services.response_loop"
SERVICE_FUNCTION = "section_staff_names"
# Decision 2: a name is `person.identity_name`, carried as `display_name`.
DISPLAY_NAME = "display_name"

# Decision 3: the survey payload's section entry gains this member.
INSTRUCTORS_FIELD = "instructors"

# Decision 4: the two tables and the spelled columns.
INSTRUCTOR_RESPONSE = "instructor_response"
RESPONSE_POLICY = "response_policy"
ROLE_COLUMN = "role"
MODE_COLUMN = "mode"
AI_SEEDED_COLUMN = "ai_seeded"
WEEK_COLUMN = "week_id"
SEQUENCE_COLUMN = "sequence"
RESPONSE_ROLES = ("INSTRUCTOR", "LEAD_FACULTY", "CHAIR")
POLICY_ROLES = ("LEAD_FACULTY", "CHAIR")
POLICY_MODES = ("ENCOURAGED", "REQUIRED")
# The ruling on B2: every column of both tables, and the ones `pulse_app` inserts.
# The fix round's F4 adds `term_id`, held by composite keys into `section (id,
# term_id)` and `week (id, term_id)`, the pattern `response` uses.
RESPONSE_COLUMNS = (
    "ai_seeded",
    "author_person_id",
    "body",
    "id",
    "published_at",
    "role",
    "section_id",
    "sequence",
    "term_id",
    "week_id",
)
RESPONSE_INSERTED = (
    "section_id",
    "term_id",
    "week_id",
    "author_person_id",
    "role",
    "ai_seeded",
    "body",
    "published_at",
)
POLICY_COLUMNS = ("id", "mode", "prefix_id", "role", "sequence", "set_at", "set_by_person_id")
POLICY_INSERTED = ("prefix_id", "set_by_person_id", "role", "mode", "set_at")
RESPONSE_SECTION_COLUMN = "section_id"
RESPONSE_TERM_COLUMN = "term_id"
# The fix round's F1 to F3: the two `BEFORE INSERT` triggers' owner.
RESPONSE_GUARD_ROLE = "pulse_response_guard_definer"
RESPONSE_AUTHOR_COLUMN = "author_person_id"
RESPONSE_BODY_COLUMN = "body"
RESPONSE_TIME_COLUMN = "published_at"
POLICY_PREFIX_COLUMN = "prefix_id"
POLICY_SETTER_COLUMN = "set_by_person_id"
POLICY_TIME_COLUMN = "set_at"
RESPONSE_TEXT_MAX_NAME = "RESPONSE_TEXT_MAX"
RESPONSE_TEXT_MAX = 4000
# Where the one constant may live. The ticket puts the records in
# `models/loop.py` and the service beside them; it does not say which holds the
# constant, so both are looked in and a constant found in neither is the failure.
RESPONSE_TEXT_MAX_HOMES = ("app.models.loop", SERVICE_MODULE)

# The migration (M1) chains from this revision (work order, "Migration M1").
M1_DOWN_REVISION = "b7d2e94c1a05"

PERSON_TABLE = "person"
SECTION_TABLE = "section"
PREFIX_TABLE = "prefix"
DEPARTMENT_TABLE = "department"
IDENTITY_NAME_COLUMN = "identity_name"

APPLICATION_ROLE = "pulse_app"
INSUFFICIENT_PRIVILEGE = "42501"
CHECK_VIOLATION = "23514"
NOT_NULL_VIOLATION = "23502"
FOREIGN_KEY_VIOLATION = "23503"
UNDEFINED_FUNCTION = "42883"

DELIVERABLE = (
    "E7-01's work order (decision 1, and the ruling on B1) settles one SECURITY DEFINER "
    "function, `public.section_staff_names(p_section_id uuid, p_reader_user_id uuid, "
    "p_reader_person_id uuid) RETURNS TABLE (person_id uuid, display_name text)`, owned by the "
    "NOLOGIN role "
    f"`{DEFINER_ROLE}`, which `{APPLICATION_ROLE}` may execute, and (decision 3) one Python door, "
    f"`{SERVICE_MODULE}.{SERVICE_FUNCTION}(session, *, section_id, reader_person_id) -> "
    "list[StaffName]`."
)

# ---------------------------------------------------------------------------
# The distinctive names. Each is planted on exactly one person, so a name found in
# an answer says who it is, and none occurs inside a uuid or another name.
# ---------------------------------------------------------------------------

TEACHER_NAME = "Odalys Fenwright-Teaches-Here"
SIBLING_SECTION_TEACHER_NAME = "Barnaby Quillfeather-Next-Door"
SIBLING_COURSE_TEACHER_NAME = "Ysolde Marchbank-Other-Course"
UNMAPPED_TEACHER_NAME = "Fourtney Ashgrove-Unled-Course"
LEAD_NAME = "Marisol Thackeray-Leads-It"
SIBLING_LEAD_NAME = "Ignatius Pellworth-Leads-Beside"
CHAIR_NAME = "Cordelia Vanstraaten-Chairs"
OTHER_CHAIR_NAME = "Hollis Brackenridge-Chairs-Elsewhere"
FORMER_TEACHER_NAME = "Wendeline Osterhout-Taught-Once"
TWO_HAT_NAME = "Rafferty Dunmore-Two-Hats"

STAFF_NAMES = (
    TEACHER_NAME,
    SIBLING_SECTION_TEACHER_NAME,
    SIBLING_COURSE_TEACHER_NAME,
    UNMAPPED_TEACHER_NAME,
    LEAD_NAME,
    SIBLING_LEAD_NAME,
    CHAIR_NAME,
    OTHER_CHAIR_NAME,
    FORMER_TEACHER_NAME,
    TWO_HAT_NAME,
)

# How far back a live enrollment starts and an ended one ends, counted from the
# real today (see the module docstring's note on the clock).
LIVE_SINCE_DAYS = 60
ENDED_DAYS_AGO = 20


# ---------------------------------------------------------------------------
# Guards on the deliverables, called from test bodies only (entry 44).
# ---------------------------------------------------------------------------


def sqlstate(failure: Any) -> str | None:
    original = getattr(failure, "orig", failure)
    for attribute in ("sqlstate", "pgcode"):
        code = getattr(original, attribute, None)
        if isinstance(code, str):
            return code
    return None


def require_the_definer(session: Any) -> None:
    """Fail, naming the deliverable, when the definer does not exist."""
    from sqlalchemy import text

    session.rollback()
    found = session.execute(
        text("SELECT to_regprocedure(:signature)"), {"signature": DEFINER_SIGNATURE}
    ).scalar_one()
    session.rollback()
    if found is None:
        pytest.fail(f"There is no `{DEFINER_SIGNATURE}`.\n\n{DELIVERABLE}")


def require_the_application_role(session: Any) -> None:
    """The session really is `pulse_app`, or every assertion measures somebody else."""
    from sqlalchemy import text

    current = session.execute(text("SELECT current_user")).scalar_one()
    session.rollback()
    assert current == APPLICATION_ROLE, (
        f"`application_session` connects as {current!r}, not `{APPLICATION_ROLE}`. A superuser "
        "passes every reader check a definer could make and every grant a test could ask about "
        "(`docs/MISTAKES.md` entry 46)."
    )


def require_the_tables(tables: dict[str, Any]) -> None:
    """Fail, naming the deliverable, when either record is not declared."""
    missing = [name for name in (INSTRUCTOR_RESPONSE, RESPONSE_POLICY) if name not in tables]
    if missing:
        pytest.fail(
            f"`Base.metadata` declares no {missing}. E7-01 owns `backend/app/models/loop.py` and "
            "M1: two append-only tables, `instructor_response` (section, course week, author, the "
            "role written under, `ai_seeded`, the text, the time, `sequence`) and "
            "`response_policy` (prefix, the person who set it, the role set under, the mode, the "
            "time, `sequence`)."
        )


def the_service_function() -> Any:
    """`app.services.response_loop.section_staff_names`, or a failure naming it."""
    try:
        module = import_module(SERVICE_MODULE)
    except ModuleNotFoundError as missing:
        if missing.name is None or not SERVICE_MODULE.startswith(missing.name):
            raise
        pytest.fail(f"`{SERVICE_MODULE}` does not exist ({missing}).\n\n{DELIVERABLE}")
    function = getattr(module, SERVICE_FUNCTION, None)
    if not callable(function):
        pytest.fail(
            f"`{SERVICE_MODULE}` exposes no callable `{SERVICE_FUNCTION}`; it exposes "
            f"{sorted(name for name in vars(module) if not name.startswith('_'))}.\n\n{DELIVERABLE}"
        )
    return function


def the_text_bound() -> int:
    """`RESPONSE_TEXT_MAX`, wherever the one constant lives, or a failure naming it."""
    found: dict[str, Any] = {}
    for home in RESPONSE_TEXT_MAX_HOMES:
        try:
            module = import_module(home)
        except ModuleNotFoundError:
            continue
        value = getattr(module, RESPONSE_TEXT_MAX_NAME, None)
        if value is not None:
            found[home] = value
    if not found:
        pytest.fail(
            f"Neither of {list(RESPONSE_TEXT_MAX_HOMES)} defines `{RESPONSE_TEXT_MAX_NAME}`. The "
            "work order (decision 4) bounds the response text by one constant, "
            f"`{RESPONSE_TEXT_MAX_NAME} = {RESPONSE_TEXT_MAX}`, mirrored by a `CHECK`."
        )
    values = set(found.values())
    assert len(values) == 1, (
        f"`{RESPONSE_TEXT_MAX_NAME}` has more than one value across {found}. The ticket: 'the "
        "bound is one constant'."
    )
    (value,) = values
    assert value == RESPONSE_TEXT_MAX, (
        f"`{RESPONSE_TEXT_MAX_NAME}` is {value!r}; the work order (decision 4) settles "
        f"{RESPONSE_TEXT_MAX} characters."
    )
    return int(value)


# ---------------------------------------------------------------------------
# Asking the channel.
# ---------------------------------------------------------------------------


class Answer(NamedTuple):
    """What one call of the definer returned: its column names and its rows."""

    columns: tuple[str, ...]
    rows: list[dict[str, Any]]

    @property
    def names(self) -> list[str]:
        return sorted(str(row.get(DISPLAY_NAME)) for row in self.rows)

    @property
    def person_ids(self) -> set[str]:
        return {str(row.get("person_id")) for row in self.rows}


def ask_the_definer(
    application_session: Any,
    *,
    section_id: Any,
    reader_user_id: Any = None,
    reader_person_id: Any = None,
) -> Answer:
    """Call the definer on `pulse_app`'s own connection; its columns and rows.

    A test names the reader by the key its session would carry: a student by
    `reader_user_id`, a member of staff by `reader_person_id` (the ruling on B1).
    Passing neither, or both, is a legal call the definer answers with nothing.
    The transaction is ended afterwards so the next call sees whatever a test
    committed in between.
    """
    from sqlalchemy import text
    from sqlalchemy.exc import DatabaseError

    def key(value: Any) -> str | None:
        return None if value is None else str(value)

    try:
        result = application_session.execute(
            text(DEFINER_CALL),
            {
                "section_id": str(section_id),
                "reader_user_id": key(reader_user_id),
                "reader_person_id": key(reader_person_id),
            },
        )
        columns = tuple(result.keys())
        rows = [dict(row) for row in result.mappings()]
    except DatabaseError as failure:
        application_session.rollback()
        if sqlstate(failure) == UNDEFINED_FUNCTION:
            pytest.fail(f"Calling `{DEFINER_SIGNATURE}` answered 42883.\n\n{DELIVERABLE}")
        raise
    application_session.rollback()
    return Answer(columns=columns, rows=rows)


def ask_the_service(
    application_session: Any, *, section_id: Any, reader_person_id: Any
) -> list[str]:
    """Call the Python door on `pulse_app`'s own connection; the names it answered.

    Staff readers only. Decision 3 settles the door's keywords as `section_id` and
    `reader_person_id`; the ruling on B1 adds a user key to the definer and does
    not say how the service takes one, so a student is asked at the definer and
    through the survey payload, never here.
    """
    function = the_service_function()
    answered = function(
        application_session, section_id=section_id, reader_person_id=reader_person_id
    )
    application_session.rollback()
    assert isinstance(answered, list), (
        f"`{SERVICE_FUNCTION}` answered {type(answered).__name__}, not a list. Work order decision "
        "3: `-> list[StaffName]`."
    )
    names: list[str] = []
    for item in answered:
        name = getattr(item, DISPLAY_NAME, None)
        if not isinstance(name, str):
            pytest.fail(
                f"`{SERVICE_FUNCTION}` answered an item {item!r} with no string `{DISPLAY_NAME}`. "
                "The definer's result column is `display_name` (work order decision 1), and this "
                "suite reads a `StaffName` by the same member; a different spelling is a one-line "
                "change in `tests/fixtures/staff_names.py`."
            )
        names.append(name)
    return sorted(names)


# ---------------------------------------------------------------------------
# The world.
# ---------------------------------------------------------------------------


class Person(NamedTuple):
    person_id: Any
    name: str
    label: str
    # The `user` row a student's person is linked to; `None` for staff planted here.
    user_id: Any = None


class StaffNameWorld:
    """E6-05's lead-review world with every staff member named. See the module docstring."""

    def __init__(
        self,
        review: LeadReviewWorld,
        web_identity: Any,
        enrol: EnrollmentRows,
        application_session: Any,
    ) -> None:
        self.review = review
        self.web_identity = web_identity
        self.enrol = enrol
        self.application_session = application_session
        self.teacher: Person | None = None
        self.sibling_section_teacher: Person | None = None
        self.sibling_course_teacher: Person | None = None
        self.unmapped_teacher: Person | None = None
        self.lead: Person | None = None
        self.sibling_lead: Person | None = None
        self.chair: Person | None = None
        self.other_chair: Person | None = None
        self.other_department: Any = None

    # -- keys ----------------------------------------------------------------

    @property
    def rows(self) -> Any:
        return self.review.rows

    @property
    def tables(self) -> dict[str, Any]:
        return self.review.world.tables

    def section_id(self, cohort: str) -> Any:
        return self.review.world.section_id(cohort)

    @property
    def taught(self) -> Any:
        """`F1WW`: the own course's section the door's instructor teaches."""
        return self.section_id(TAUGHT_COHORT)

    @property
    def sibling_section(self) -> Any:
        """`Q1WW`: the own course's other section."""
        return self.section_id(UNTAUGHT_COHORT)

    @property
    def sibling_course_section(self) -> Any:
        return self.section_id(SIBLING_COHORT)

    @property
    def unmapped_section(self) -> Any:
        return self.section_id(UNMAPPED_COHORT)

    def every_section(self) -> dict[str, Any]:
        return {
            "the taught section": self.taught,
            "the sibling section": self.sibling_section,
            "the sibling course's section": self.sibling_course_section,
            "the unmapped course's section": self.unmapped_section,
        }

    # -- planting ------------------------------------------------------------

    def name(self, person_id: Any, name: str) -> None:
        """Write `name` into one person's `identity_name`, committed."""
        table = require_table(self.tables, PERSON_TABLE)
        key = single_primary_key(table)
        self.rows.session.execute(
            table.update().where(table.c[key] == person_id).values(**{IDENTITY_NAME_COLUMN: name})
        )
        self.rows.commit()

    def a_named_person(self, name: str) -> Any:
        return self.web_identity.person(**{IDENTITY_NAME_COLUMN: name})

    def teaches(self, person_id: Any, section_id: Any) -> Any:
        """A live section-scoped `INSTRUCTOR` assignment, committed; its row."""
        row = self.review.graph.assign(INSTRUCTOR_ROLE, scope=section_id, person=person_id)
        self.rows.commit()
        return row

    def a_teacher_of(self, section_id: Any, name: str, label: str) -> Person:
        person = self.a_named_person(name)
        self.teaches(person, section_id)
        return Person(person_id=person, name=name, label=label)

    def a_student(
        self, label: str, section_id: Any, *, ended: bool = False, with_person: bool = False
    ) -> Person:
        """A `user` enrolled in `section_id`, live or ended — a student as a launch leaves one.

        A launched student has a `user` row and no `person` (ADR 0028), so by
        default none is planted and `person_id` is `None`; the definer is asked
        about a student by `user_id` (the ruling on B1). `with_person` adds a named
        `person` linked to the user — the shape of a student who also holds a staff
        hat, and of a student whose name is planted to see whether it ever comes
        back.
        """
        name = f"Student {label} Quorvane-{uuid4().hex[:6]}"
        person = self.a_named_person(name) if with_person else None
        subject = f"e7-01-{label}-{uuid4().hex[:8]}"
        user = self.web_identity.user(platform_id=self.review._platform_id(), subject=subject)
        if person is not None:
            self.web_identity.link_person_to_user(person_id=person, user_id=user)
        today = datetime.now(UTC).date()
        self.enrol.enrol(
            user_id=user,
            section_id=section_id,
            started_on=today - timedelta(days=LIVE_SINCE_DAYS),
            ended_on=today - timedelta(days=ENDED_DAYS_AGO) if ended else None,
        )
        return Person(person_id=person, name=name, label=label, user_id=user)

    def a_former_teacher_of_the_taught_section(self) -> Person:
        """A person whose `INSTRUCTOR` grant on `F1WW` the roster's own writer has ended.

        `tests/integration/test_an_ended_teaching_grant_still_keeps_its_section_out_
        of_the_leaders_review.py::taught_then_ended`, copied rather than adapted
        (`docs/MISTAKES.md` entry 37): the grant is ended by the ending definer on
        `pulse_app`'s connection, citing a successful roster call of the section,
        and both halves are read back before the person is handed over.
        """
        session = self.rows.session
        require_the_grant_ending_definer(session)
        require_the_ended_teaching_grant_table(session)
        person = self.a_named_person(FORMER_TEACHER_NAME)
        section = self.taught
        row = self.teaches(person, section)
        assignment_id = row[self.review.graph.assignment_key]
        call = self.rows.seed(
            "nrps_call",
            {},
            section_id=section,
            url=f"https://roster.e7-01.invalid/{uuid4().hex[:12]}",
            response_code=200,
            members_seen=1,
            called_at=datetime.now(UTC),
        )
        self.rows.commit()

        from sqlalchemy import text

        self.application_session.execute(
            text(END_TEACHING_INSTRUCTOR_CALL),
            {
                "assignment_id": assignment_id,
                "nrps_call_id": call["id"],
                "ended_on": institution_today(),
            },
        )
        self.application_session.commit()

        assert not self.review.graph.assignments_of(person), (
            "The former teacher still holds an assignment after the ending: the grant was not "
            "ended, so this world's 'former teacher' is a live one."
        )
        recorded = [
            ended
            for ended in ended_teaching_grants(session)
            if str(ended["assignment_id"]) == str(assignment_id)
        ]
        assert len(recorded) == 1 and str(recorded[0]["section_id"]) == str(section), (
            f"The ending left {recorded} in `ended_teaching_grant`; the roster's writer records "
            "exactly one row naming the section."
        )
        return Person(person_id=person, name=FORMER_TEACHER_NAME, label="the former teacher")

    def a_two_hat_person(self) -> Person:
        """A student in `Q1WW` (section A) who teaches the sibling course's section (B).

        The ticket's own case: "a two-hat person who is a student in section A and
        an instructor in section B, asking for section C" — C is `F1WW`. One
        person, linked to one user: the user key is their student session's, the
        person key their instructor session's.
        """
        student = self.a_student("two-hat", self.sibling_section, with_person=True)
        self.name(student.person_id, TWO_HAT_NAME)
        self.teaches(student.person_id, self.sibling_course_section)
        return Person(
            person_id=student.person_id,
            name=TWO_HAT_NAME,
            label="the two-hat person",
            user_id=student.user_id,
        )

    def a_response(self, section_id: Any, *, author: Any, role: str) -> Any:
        """One `instructor_response` row for `section_id`, written by `author` under `role`.

        Every column the ruling on B2 and the fix round's F4 settle is named; the
        week is one of the section's own term's weeks. **The author must hold
        `role` for the section** — the fix round's F1 trigger refuses anyone else
        even on the seeding connection — so every caller passes a person this
        world gave that grant (the section's teacher as `INSTRUCTOR`, the course's
        lead as `LEAD_FACULTY`). One author per section-week (F2) holds too: no
        caller writes two authors into one section's week.
        """
        require_the_tables(self.tables)
        values = {
            RESPONSE_SECTION_COLUMN: section_id,
            RESPONSE_TERM_COLUMN: self.term_of(section_id),
            RESPONSE_AUTHOR_COLUMN: author,
            ROLE_COLUMN: role,
            AI_SEEDED_COLUMN: False,
            RESPONSE_BODY_COLUMN: f"E7-01 a response by {author} to {section_id}",
            RESPONSE_TIME_COLUMN: datetime.now(UTC),
            WEEK_COLUMN: self.a_week_of(section_id),
        }
        row = self.rows.seed(INSTRUCTOR_RESPONSE, {}, **values)
        self.rows.commit()
        return row

    def term_of(self, section_id: Any) -> Any:
        """The `term` key the section's own row names."""
        section_table = require_table(self.tables, SECTION_TABLE)
        self.rows.session.rollback()
        section = (
            self.rows.session.execute(
                section_table.select().where(
                    section_table.c[single_primary_key(section_table)] == section_id
                )
            )
            .mappings()
            .one()
        )
        terms = foreign_key_columns(section_table, "term")
        if len(terms) != 1:
            pytest.fail(f"`section` has {len(terms)} references to `term` ({terms}).")
        return section[terms[0]]

    def a_week_of(self, section_id: Any, index: int = 0) -> Any:
        """The `index`-th `week` of the section's own term, by week number."""
        week_table = require_table(self.tables, "week")
        week_terms = id_references(week_table, "term")
        if len(week_terms) != 1:
            pytest.fail(f"`week` has {len(week_terms)} references to `term` ({week_terms}).")
        term = self.term_of(section_id)
        statement = week_table.select().where(week_table.c[week_terms[0]] == term)
        if "number" in week_table.c:
            statement = statement.order_by(week_table.c["number"])
        found = self.rows.session.execute(statement).mappings().all()
        self.rows.session.rollback()
        if len(found) <= index:
            pytest.fail(f"The section's term has {len(found)} weeks; week {index} was asked for.")
        return found[index][single_primary_key(week_table)]


def id_references(table: Any, target: str) -> list[str]:
    """The columns of `table` whose foreign key refers to `target.id`, sorted.

    Narrower than `foreign_key_columns`, which counts every column of every key
    pointing at `target`: a composite key such as `week (term_id,
    term_length_weeks) → term (id, length_weeks)`, or F4's `instructor_response
    (section_id, term_id) → section (id, term_id)`, is one reference whose other
    columns refer to something other than the target's `id`
    (`docs/disputes/E7-01-01.md`).
    """
    return sorted(
        {
            key.parent.name
            for key in table.foreign_keys
            if key.column.table.name == target and key.column.name == "id"
        }
    )


def only_reference(table: Any, target: str) -> str:
    """The one column of `table` referring to `target.id`, or a failure naming both."""
    columns = id_references(table, target)
    if len(columns) != 1:
        pytest.fail(
            f"`{table.name}` has {len(columns)} references to `{target}` ({columns}); the ticket "
            f"lists one ({INSTRUCTOR_RESPONSE}: the section and the author; {RESPONSE_POLICY}: "
            "the prefix and the person who set it)."
        )
    return columns[0]


def build_staff_name_world(
    review: LeadReviewWorld,
    web_identity: Any,
    enrol: EnrollmentRows,
    application_session: Any,
) -> StaffNameWorld:
    """Name everyone, add the three teachers and the second department's chair.

    **The premise checks at the foot are this fixture's**: they are claims about
    the rows written here and not about anything E7-01 owes, so a failure in them
    is a defect in this world (`docs/MISTAKES.md` entry 13).
    """
    world = StaffNameWorld(review, web_identity, enrol, application_session)
    # The clock: see the module docstring.
    review.door.door.pretend(datetime.now(UTC))

    assert review.lead is not None and review.sibling_lead is not None
    assert review.chair is not None
    teacher_id = review.door.door.person_id
    assert teacher_id is not None, "The report door's instructor has no person."

    for person_id, name in (
        (teacher_id, TEACHER_NAME),
        (review.lead.person_id, LEAD_NAME),
        (review.sibling_lead.person_id, SIBLING_LEAD_NAME),
        (review.chair.person_id, CHAIR_NAME),
    ):
        world.name(person_id, name)
    world.teacher = Person(teacher_id, TEACHER_NAME, "the taught section's instructor")
    world.lead = Person(review.lead.person_id, LEAD_NAME, "the lead")
    world.sibling_lead = Person(review.sibling_lead.person_id, SIBLING_LEAD_NAME, "a sibling lead")
    world.chair = Person(review.chair.person_id, CHAIR_NAME, "the department's chair")

    world.sibling_section_teacher = world.a_teacher_of(
        world.sibling_section, SIBLING_SECTION_TEACHER_NAME, "the sibling section's instructor"
    )
    world.sibling_course_teacher = world.a_teacher_of(
        world.sibling_course_section, SIBLING_COURSE_TEACHER_NAME, "the sibling course's instructor"
    )
    world.unmapped_teacher = world.a_teacher_of(
        world.unmapped_section, UNMAPPED_TEACHER_NAME, "the unmapped course's instructor"
    )

    chain = review.world.calendar.chain
    above = {level: chain[level] for level in ("institution", COLLEGE_TABLE) if level in chain}
    department = review.rows.seed(DEPARTMENT_TABLE, above)
    review.rows.commit()
    world.other_department = department[
        single_primary_key(require_table(world.tables, DEPARTMENT_TABLE))
    ]
    other = review.a_leader("e7-01-other-chair", grants=((CHAIR_ROLE, world.other_department),))
    world.name(other.person_id, OTHER_CHAIR_NAME)
    world.other_chair = Person(other.person_id, OTHER_CHAIR_NAME, "another department's chair")

    assert str(world.other_department) != str(
        review.department
    ), "The second department is the first one: a chair of it would be the chair again."
    sections = list(world.every_section().values())
    assert (
        len({str(section) for section in sections}) == 4
    ), f"The four sections of this world are not four rows: {sections}."
    return world


@pytest.fixture
def staff_names(
    lead_review: LeadReviewWorld,
    web_identity: Any,
    enrol: EnrollmentRows,
    application_session: Any,
) -> Iterator[StaffNameWorld]:
    """The lead-review world with every staff member named. See the module docstring.

    Builds nothing E7-01 owes: the definer and the service are looked up inside
    each test body (`docs/MISTAKES.md` entry 44).
    """
    yield build_staff_name_world(lead_review, web_identity, enrol, application_session)
