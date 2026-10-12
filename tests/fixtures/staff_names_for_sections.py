"""E9-03 — the staff-name channel over a set of sections, and the world it is read over.

Three test modules ask the same set-based channel the same questions, so the
driving lives here and each module asserts (`docs/MISTAKES.md` entry 13). Nothing
in this repository answers any of it yet.

**The names E9-03's settlement fixes, transcribed once** (the coordinator's
ruling of 2026-10-12, adopting the test author's proposed settlement as written):

  - the definer is an overload, `public.section_staff_names(p_section_ids uuid[],
    p_reader_user_id uuid, p_reader_person_id uuid, p_reader_date date)`,
    returning `(section_id, role, person_id, display_name)`. v001
    (`section_staff_names(uuid,uuid,uuid)`) stays. Both are owned by
    `pulse_staff_name_definer`;
  - the role values are `INSTRUCTOR`, `AUTHOR`, `LEAD_FACULTY`, `CHAIR` and
    `DEAN`; one row per (section, role, person), so a teacher who also wrote a
    response is two rows; the dean row comes from a `DEAN` assignment only;
  - the door is `app.services.response_loop.section_staff_names(session, *,
    section_ids, reader_user_id=None, reader_person_id=None, scope=None) ->
    list[StaffName]`, and `StaffName` carries `section_id`, `role`, `person_id`
    and `display_name`. Given a leadership scope, the door passes the definer only
    the sections in it. It takes the reader's date from `services.clock.now` in
    the institution's timezone;
  - ruling 3 as narrowed by README decision 16: a reader holding a live `CHAIR`,
    `ASSISTANT_DEAN`, `DEAN` or `VP_ACADEMICS` assignment is answered for any
    section passed; a reader whose only leadership is `LEAD_FACULTY` keeps v001's
    per-section check.

**The world** is E7-01's staff-name world (`tests/fixtures/staff_names.py`), which
is E6-05's lead-review world with every member of staff named. Added here, each by
a method a test calls so the test's own body says which of them its world holds:

  - a dean, an assistant dean, a vice president, a Care-only person and an
    Admin-only person, each with a distinctive name;
  - a section in a **second department of the same college that has no chair**,
    with its own named instructor (the "department with no chair" of done-when 2,
    and the out-of-purview section for a chair in done-when 5);
  - a bare new department, for a lead who also chairs somewhere else;
  - a student whose enrollment dates the test names, for the clock case.

**Every read is made on `pulse_app`'s own connection** (`application_session`,
`docs/MISTAKES.md` entry 46). **Every guard on a deliverable is a plain function
called from a test body**, so an unbuilt tree is a FAILED naming it, never an
ERROR in setup (`docs/MISTAKES.md` entry 44). **Nothing here decides an answer**:
it plants, calls and reads back, and every expectation is written out in the test
that makes it (`docs/MISTAKES.md` entries 19 and 30).
"""

import inspect
import re
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import date
from typing import Any, NamedTuple
from uuid import uuid4

import pytest

from fixtures.lead_review import COLLEGE_TABLE, DEPARTMENT_TABLE
from fixtures.staff_names import (
    DEFINER_SIGNATURE,
    UNDEFINED_FUNCTION,
    Person,
    StaffNameWorld,
    require_the_application_role,
    sqlstate,
    the_service_function,
)
from fixtures.student_read import COURSE_TABLE, PREFIX_TABLE
from fixtures.supervision import require_table, single_primary_key
from fixtures.survey_windows import SECTION_TABLE

# ---------------------------------------------------------------------------
# The names E9-03's settlement fixes, spelled once.
# ---------------------------------------------------------------------------

V1_SIGNATURE = DEFINER_SIGNATURE
V2_SIGNATURE = "public.section_staff_names(uuid[],uuid,uuid,date)"
DEFINER_NAME = "section_staff_names"
# Cast, never `::`, for the reason `tests/fixtures/staff_names.py::DEFINER_CALL`
# gives; the array cast is `tests/fixtures/benchmark_views.py`'s.
V2_CALL = (
    "SELECT * FROM public.section_staff_names("
    "CAST(:section_ids AS uuid[]), CAST(:reader_user_id AS uuid), "
    "CAST(:reader_person_id AS uuid), CAST(:reader_date AS date))"
)
V2_COLUMNS = ("section_id", "role", "person_id", "display_name")

AS_INSTRUCTOR = "INSTRUCTOR"
AS_AUTHOR = "AUTHOR"
AS_LEAD = "LEAD_FACULTY"
AS_CHAIR = "CHAIR"
AS_DEAN = "DEAN"
V2_ROLES = frozenset({AS_INSTRUCTOR, AS_AUTHOR, AS_LEAD, AS_CHAIR, AS_DEAN})

# The door's keywords. `StaffName`'s members are `V2_COLUMNS`.
DOOR_KEYWORDS = ("section_ids", "reader_user_id", "reader_person_id", "scope")

# The assignment roles planted here, in `tests/fixtures/supervision.py`'s
# `ROLE_ALIASES` spelling.
DEAN_ROLE = "DEAN"
ASSISTANT_DEAN_ROLE = "ASSISTANT_DEAN"
VP_ROLE = "VP_ACADEMICS"
CHAIR_ROLE = "CHAIR"
CARE_ROLE = "CARE"
ADMIN_ROLE = "ADMIN"
INSTITUTION_TABLE = "institution"

SETTLEMENT = (
    "E9-03's settlement (2026-10-12): the definer is the overload "
    "`public.section_staff_names(p_section_ids uuid[], p_reader_user_id uuid, "
    "p_reader_person_id uuid, p_reader_date date)` returning `(section_id, role, person_id, "
    "display_name)`, owned by `pulse_staff_name_definer`, with v001 kept beside it; the door is "
    "`app.services.response_loop.section_staff_names(session, *, section_ids, "
    "reader_user_id=None, reader_person_id=None, scope=None) -> list[StaffName]`, `StaffName` "
    "carrying `section_id`, `role`, `person_id` and `display_name`."
)

# A cohort no other world uses under the report world's term (`SEEDED_COHORTS`):
# `X` is the report world's second taught cohort, and `F`, `Q`, `Y`, `4` and `R`
# are taken by the worlds this one is built on.
CHAIRLESS_COHORT = "Z"

# The distinctive names. Each is planted on exactly one person.
DEAN_NAME = "Theodora Wexcombe-Dean-Of-College"
ASSISTANT_DEAN_NAME = "Lucan Harrowgate-Assistant-Dean"
VP_NAME = "Marguerite Ostrander-Vice-President"
CARE_NAME = "Sabine Coldharbour-Care-Only"
ADMIN_NAME = "Desmond Fairweather-Admin-Only"
NOBODY_NAME = "Perrin Ashcombe-Holds-Nothing"
CHAIRLESS_TEACHER_NAME = "Zenobia Pickering-No-Chair-Above"


# ---------------------------------------------------------------------------
# Guards on the deliverables, called from test bodies only (entry 44).
# ---------------------------------------------------------------------------


def require_v2(session: Any) -> None:
    """Fail, naming the settlement, when the set-based overload does not exist."""
    from sqlalchemy import text

    session.rollback()
    found = session.execute(
        text("SELECT to_regprocedure(:signature)"), {"signature": V2_SIGNATURE}
    ).scalar_one()
    session.rollback()
    if found is None:
        pytest.fail(f"There is no `{V2_SIGNATURE}`.\n\n{SETTLEMENT}")


def prepared(world: StaffNameWorld) -> None:
    """The session is `pulse_app`, and the overload exists."""
    require_the_application_role(world.application_session)
    require_v2(world.application_session)


def the_set_door() -> Any:
    """`response_loop.section_staff_names`, or a failure when it does not take `section_ids`."""
    function = the_service_function()
    parameters = inspect.signature(function).parameters
    missing = [name for name in DOOR_KEYWORDS if name not in parameters]
    if missing:
        declared = inspect.signature(function)
        pytest.fail(f"`section_staff_names{declared}` takes no {missing}.\n\n{SETTLEMENT}")
    return function


# ---------------------------------------------------------------------------
# Asking the channel.
# ---------------------------------------------------------------------------


class Row(NamedTuple):
    """One answered row, every key as a string so rows compare across drivers."""

    section_id: str
    role: str
    person_id: str
    display_name: str

    @property
    def triple(self) -> tuple[str, str, str]:
        return (self.section_id, self.role, self.person_id)


class SetAnswer(NamedTuple):
    """One call's column names and rows."""

    columns: tuple[str, ...]
    rows: list[Row]

    def of(self, section_id: Any) -> list[Row]:
        return [row for row in self.rows if row.section_id == str(section_id)]

    @property
    def sections(self) -> set[str]:
        return {row.section_id for row in self.rows}

    @property
    def triples(self) -> set[tuple[str, str, str]]:
        return {row.triple for row in self.rows}


def _key(value: Any) -> str | None:
    return None if value is None else str(value)


def _row(found: Any, what: str) -> Row:
    """A `Row` out of a mapping or an object, or a failure naming the settled members."""
    values: dict[str, Any] = {}
    for member in V2_COLUMNS:
        value = found.get(member) if isinstance(found, dict) else getattr(found, member, None)
        if value is None:
            pytest.fail(f"{what} answered {found!r}, which carries no `{member}`.\n\n{SETTLEMENT}")
        values[member] = str(getattr(value, "value", value))
    return Row(**values)


def ask_v2(
    application_session: Any,
    *,
    section_ids: Sequence[Any],
    reader_date: date,
    reader_user_id: Any = None,
    reader_person_id: Any = None,
) -> SetAnswer:
    """Call the overload on `pulse_app`'s own connection; its columns and rows.

    `reader_date` has no default: which day the reader is asked on is what the
    clock tests are about, and every other caller names the institution's real
    today (`fixtures.roster_sync.institution_today`). An enum-typed `role` is read
    by its value, so the comparison is with the settled spelling either way.
    """
    from sqlalchemy import text
    from sqlalchemy.exc import DatabaseError

    try:
        result = application_session.execute(
            text(V2_CALL),
            {
                "section_ids": [str(value) for value in section_ids],
                "reader_user_id": _key(reader_user_id),
                "reader_person_id": _key(reader_person_id),
                "reader_date": reader_date,
            },
        )
        columns = tuple(result.keys())
        found = [dict(row) for row in result.mappings()]
    except DatabaseError as failure:
        application_session.rollback()
        if sqlstate(failure) == UNDEFINED_FUNCTION:
            pytest.fail(f"Calling `{V2_SIGNATURE}` answered 42883.\n\n{SETTLEMENT}")
        raise
    application_session.rollback()
    if set(columns) != set(V2_COLUMNS):
        pytest.fail(
            f"`{V2_SIGNATURE}` answered columns {columns}, not {V2_COLUMNS}.\n\n{SETTLEMENT}"
        )
    return SetAnswer(columns=columns, rows=[_row(row, f"`{V2_SIGNATURE}`") for row in found])


def ask_the_set_door(
    application_session: Any,
    *,
    section_ids: Sequence[Any],
    reader_user_id: Any = None,
    reader_person_id: Any = None,
    scope: Any,
) -> list[Row]:
    """Call the door on `pulse_app`'s own connection; the rows it answered.

    `scope` has no default here either: the E9-03 fix round made it a required
    keyword on the door, so every call site says whether it filters by a purview.
    """
    function = the_set_door()
    answered = function(
        application_session,
        section_ids=list(section_ids),
        reader_user_id=reader_user_id,
        reader_person_id=reader_person_id,
        scope=scope,
    )
    application_session.rollback()
    assert isinstance(
        answered, list
    ), f"The door answered {type(answered).__name__}, not a list.\n\n{SETTLEMENT}"
    return [_row(item, "The door") for item in answered]


def rows_of(rows: list[Row], section_id: Any) -> list[Row]:
    return [row for row in rows if row.section_id == str(section_id)]


# ---------------------------------------------------------------------------
# Watching the wire: every statement and its parameters, while one call runs.
# ---------------------------------------------------------------------------


class SentStatement(NamedTuple):
    """One statement as the driver was handed it, and its parameters rendered."""

    sql: str
    parameters: str

    @property
    def text(self) -> str:
        return f"{self.sql}\n{self.parameters}"


# A call of the definer, by name, in whatever spelling a statement carries it.
DEFINER_CALLED = re.compile(r"\bsection_staff_names\s*\(", re.IGNORECASE)


@contextmanager
def statements_sent() -> Iterator[list[SentStatement]]:
    """Every statement and its parameters sent to any engine while the block runs.

    `tests/fixtures/statements.py::statements_recorded`, with the parameters kept:
    the door's job in done-when 5 is a property of what it binds, not of the SQL
    text. Listening on the `Engine` class sees the connection `application_session`
    rides. The listener is removed in a `finally`, for that module's reason.
    """
    from sqlalchemy import event
    from sqlalchemy.engine import Engine

    recorded: list[SentStatement] = []

    def record(
        connection: Any,
        cursor: Any,
        statement: str,
        parameters: Any,
        context: Any,
        executemany: bool,
    ) -> None:
        recorded.append(SentStatement(str(statement), repr(parameters)))

    event.listen(Engine, "before_cursor_execute", record)
    try:
        yield recorded
    finally:
        event.remove(Engine, "before_cursor_execute", record)


def definer_calls(recorded: list[SentStatement]) -> list[SentStatement]:
    return [statement for statement in recorded if DEFINER_CALLED.search(statement.sql)]


# ---------------------------------------------------------------------------
# The world.
# ---------------------------------------------------------------------------


class SetWorld:
    """E7-01's staff-name world, with the readers and the section E9-03 asks about."""

    def __init__(self, names: StaffNameWorld) -> None:
        self.names = names
        self.chairless_section: Any = None
        self.chairless_department: Any = None
        self.chairless_teacher: Person | None = None

    @property
    def review(self) -> Any:
        return self.names.review

    @property
    def session(self) -> Any:
        return self.names.application_session

    def chain_key(self, level: str) -> Any:
        """The key of one containment level of the report world's chain."""
        chain = self.review.world.calendar.chain
        if level not in chain:
            pytest.fail(
                f"The report world's chain holds {sorted(chain)} and no `{level}`; this world "
                "needs it to scope a grant. A broken world, not a red."
            )
        return self.review.key(level, chain[level])

    @property
    def institution(self) -> Any:
        return self.chain_key(INSTITUTION_TABLE)

    @property
    def college(self) -> Any:
        return self.review.college

    def a_person_holding(
        self,
        label: str,
        name: str,
        grants: tuple[tuple[str, Any], ...],
        *,
        with_user: bool = False,
    ) -> Person:
        """A named person holding exactly `grants` (role, scope key), committed.

        `with_user` links a `user` row as well, the shape of a person who can
        sign in, so a test can ask about them by user key.
        """
        person = self.names.a_named_person(name)
        for role, scope in grants:
            self.review.graph.assign(role, scope=scope, person=person)
        user = None
        if with_user:
            user = self.names.web_identity.user(
                platform_id=self.review._platform_id(), subject=f"e9-03-{uuid4().hex[:8]}"
            )
            self.names.web_identity.link_person_to_user(person_id=person, user_id=user)
        self.review.rows.commit()
        return Person(person_id=person, name=name, label=label, user_id=user)

    def a_dean(self) -> Person:
        return self.a_person_holding(
            "the college's dean", DEAN_NAME, ((DEAN_ROLE, self.college),), with_user=True
        )

    def an_assistant_dean(self) -> Person:
        grants = ((ASSISTANT_DEAN_ROLE, self.college),)
        return self.a_person_holding("the college's assistant dean", ASSISTANT_DEAN_NAME, grants)

    def a_vice_president(self) -> Person:
        return self.a_person_holding("the vice president", VP_NAME, ((VP_ROLE, self.institution),))

    def a_care_holder(self) -> Person:
        grants = ((CARE_ROLE, self.institution),)
        return self.a_person_holding("a Care-only person", CARE_NAME, grants)

    def an_admin(self) -> Person:
        grants = ((ADMIN_ROLE, self.institution),)
        return self.a_person_holding("an Admin-only person", ADMIN_NAME, grants)

    def a_person_holding_nothing(self) -> Person:
        return self.a_person_holding("a person holding nothing", NOBODY_NAME, (), with_user=True)

    def a_new_department(self) -> Any:
        """A bare department under the report world's college, committed; its key."""
        chain = self.review.world.calendar.chain
        levels = (INSTITUTION_TABLE, COLLEGE_TABLE)
        above = {level: chain[level] for level in levels if level in chain}
        department = self.review.rows.seed(DEPARTMENT_TABLE, above)
        self.review.rows.commit()
        key = department[single_primary_key(require_table(self.names.tables, DEPARTMENT_TABLE))]
        assert str(key) != str(
            self.review.department
        ), "The new department is the report world's own one. A broken world, not a red."
        return key

    def a_section_in_a_department_with_no_chair(self) -> Any:
        """A cohort-`Z` section under a new prefix, in a new department of the same college.

        `tests/fixtures/lead_review.py::_a_course_beside_the_own_one`, copied rather
        than adapted (`docs/MISTAKES.md` entry 37), with the prefix and the
        department popped as well, so the walker invents a department under the
        report world's college. Nobody holds `CHAIR` on it. A named instructor is
        planted on the section, so a reader of it has a name to be answered.

        **The premise checks at the foot are this fixture's**: the new department
        is neither the report world's nor E7-01's second one, and it sits under the
        same college. A failure there is a broken world, not a red.
        """
        world = self.review.world
        calendar = world.calendar
        saved = calendar.chain
        branch = dict(saved)
        for level in (SECTION_TABLE, COURSE_TABLE, PREFIX_TABLE, DEPARTMENT_TABLE):
            branch.pop(level, None)
        calendar.chain = branch
        try:
            world.section(CHAIRLESS_COHORT)
        finally:
            calendar.chain = saved
        self.review.rows.commit()
        for level in (DEPARTMENT_TABLE, COLLEGE_TABLE):
            if level not in branch:
                pytest.fail(
                    f"Seeding a cohort-{CHAIRLESS_COHORT} section on a chain without a department "
                    f"left no `{level}` in it ({sorted(branch)}). A broken world, not a red."
                )
        department = self.review.key(DEPARTMENT_TABLE, branch[DEPARTMENT_TABLE])
        college = self.review.key(COLLEGE_TABLE, branch[COLLEGE_TABLE])
        assert str(department) not in {
            str(self.review.department),
            str(self.names.other_department),
        }, "The chairless section landed in a department that has a chair. A broken world."
        assert str(college) == str(self.college), (
            f"The chairless section's department sits under college {college}, not the report "
            f"world's {self.college}, so its dean would be nobody here. A broken world."
        )
        self.chairless_department = department
        self.chairless_section = world.section_id(CHAIRLESS_COHORT)
        self.chairless_teacher = self.names.a_teacher_of(
            self.chairless_section, CHAIRLESS_TEACHER_NAME, "the chairless section's instructor"
        )
        return self.chairless_section

    def a_student_enrolled(
        self, label: str, section_id: Any, *, started_on: date, ended_on: date | None
    ) -> Person:
        """A `user` enrolled in `section_id` between the dates the caller names; no `person`."""
        user = self.names.web_identity.user(
            platform_id=self.review._platform_id(), subject=f"e9-03-{label}-{uuid4().hex[:8]}"
        )
        self.names.enrol.enrol(
            user_id=user, section_id=section_id, started_on=started_on, ended_on=ended_on
        )
        return Person(person_id=None, name="", label=label, user_id=user)


@pytest.fixture
def staff_names_for_sections(staff_names: StaffNameWorld) -> SetWorld:
    """E7-01's staff-name world, ready for the set-based questions. See the module docstring.

    Builds nothing E9-03 owes: the overload and the door are looked up inside each
    test body (`docs/MISTAKES.md` entry 44).
    """
    return SetWorld(staff_names)
