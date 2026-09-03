"""E2-09 — the world a student's read path answers over, and the door it is read through.

Two modules need the same three things and neither may hold its own copy
(`docs/MISTAKES.md` entry 13): the names E2-09's work order settles, a student
who is enrolled in one section and not in its sibling, and a way to ask
`GET /student/survey` as that student over HTTP.

**Why the rows are committed and the read goes over HTTP.** The tool opens its
own connection out of `DATABASE_URL` and sees nothing that has not been
committed, exactly as `tests/fixtures/landing.py` and
`tests/fixtures/web_identity.py` say of every door in this suite. So everything
here rides `committed_rows`, and the session a read is made with is one a real
launch issued rather than one this file minted — which is also why no test in
either module has to know how `issue_session` spells its arguments.

**What this fixture chooses, and what it refuses to choose.** It seeds rows: a
term, two sections of it, one window each, a question set, three people with an
enrollment each, and two submissions that are not the reader's. Those are *inputs*
to the read path and the tests read them back as outputs, which is what a
read-path test is; nothing here encodes what the answer should look like. The two
things a test could be about — which instant the clock pretends, and whether the
student has submitted anything — are not decided here: `pretend` takes the
instant, and `submit_own` is a call the test makes or does not
(`docs/MISTAKES.md` entry 30).

**The two sections are siblings under one course, on purpose.** `Fall2026`
(`tests/fixtures/survey_windows.py`) seeds every section it is asked for under
one containment chain, so section B differs from section A in its own row and in
nothing above it — which is the shape a query that joins on the course, or on the
term, or on the week, answers with both. Both carry a window over the same term
week, so at the instant a test reads, B is open too.

**Three people, and the third one is the whole of what makes the headline
mutation die.** The reader and a classmate are enrolled in section A; a third
person is enrolled in section B and has submitted there. That third enrollment was
missing when this file was first written, and the mutation battery measured what
it cost: with `Enrollment.user_id == user_id` deleted from the read's own
`_live_enrollments`, the query returned *every* live enrollment — and every live
enrollment was in section A, so the widened read reached exactly the rows the
correct read reaches and all 2430 tests stayed green. The paragraph that used to
stand here claimed a lost enrollment predicate would have something to return,
and that was true only of the join-widened variants — a read widened to the
course, to the term or to the week — which the same battery killed.

So the rule is seeded as rows rather than asserted as prose: **for every way of
losing the student predicate there is a B-shaped row to leak** — a section, a
window, an enrollment, and a stored submission, none of them the reader's.
`test_the_student_read_path_names_nothing_outside_the_enrollment.py` requires
those rows to exist before it reports that they did not come back, so the shape
this file has to keep is an assertion over there rather than a sentence here.

**Term week 13 is chosen because two of SPEC §2.2's cohorts are live in it and
neither one starts there.** `D` runs fifteen weeks from term week 4 and `Q` runs
twelve from term week 7, so the same week is each section's tenth and seventh
course week — which is what makes §2.2's two week numbers tell each other apart.
A pair of sections whose window sat in their own first week would answer 1 and 13,
and a course week of 1 is a number a hard-coded field also produces. The window
instants are `WINDOWS_BY_TERM_WEEK[13]`, the hand-written table E2-06's suites
are measured against, so nothing here re-derives SPEC §3.1's rhythm and agrees
with an implementation that got it wrong.

**The names below are the settled contract, transcribed once.** E2-09's work
order settles the route, the student-session dependency and the copy registry
before any code is written, so a name that turns out to be wrong is one line here
rather than a rewrite of two modules — the convention `tests/fixtures/landing.py`
sets out for E1-13's `landing_contract`.

**The environment** (`docs/MISTAKES.md` entry 40): everything here rides
`launch_driver_in`, which rides `tool_doors` and therefore `configured_env` — the
development name, laid down before the application is imported. It has to be that
name: ADR 0109 applies the `clock_override` row only where the environment is the
development one, and every open/closed case in E2-09 moves that clock.
`student_read_door_in` is how a test names a *further* value for that laying-down
— FIX-01's institution timezone is the first — and `student_read_door` is that
factory called with nothing.
"""

import json
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from importlib import import_module
from types import ModuleType
from typing import Any, NamedTuple
from uuid import UUID

import pytest

from fixtures.provisioning import INSTRUCTOR_ROLE_URN, LEARNER_ROLE_URN
from fixtures.supervision import (
    foreign_key_columns,
    require_column,
    require_table,
    single_primary_key,
)
from fixtures.survey_windows import (
    COHORT_SECTION_MODALITY,
    COHORT_SECTION_ORDINAL,
    SECTION_CODE_COLUMN,
    SECTION_END_COLUMN,
    SECTION_LENGTH_COLUMN,
    SECTION_START_COLUMN,
    SECTION_TABLE,
    SEEDED_COHORTS,
    SURVEY_WINDOW_TABLE,
    TERM_TABLE,
    WEEK_TABLE,
    WINDOW_CLOSES_COLUMN,
    WINDOW_OPENS_COLUMN,
    WINDOW_SECTION_COLUMN,
    WINDOW_TERM_COLUMN,
    WINDOW_WEEK_COLUMN,
    WINDOWS_BY_TERM_WEEK,
    Fall2026,
)

# ---------------------------------------------------------------------------
# The names E2-09's work order settles, transcribed once.
# ---------------------------------------------------------------------------

# The route, and the whole of its interface: no path parameters and no query
# parameters. It answers "for me, right now, what is there?" for every live
# enrollment of the session's user, in one round trip (criterion 1).
STUDENT_READ_PATH = "/student/survey"

# The two week fields the answer carries, spelled exactly. **Ruled from SPEC §2.2
# (docs/SPEC.md:82) rather than chosen here**: a student's course-level page plots
# the *course* week with a quiet term-week sub-label, so the answer carries both
# and E2-10 renders one under the other. `course_week` is the ordinal from the
# section's own start — the window's term week minus the section's first active
# term week, plus one — and `term_week` is the window's week row's `number`.
#
# These are the only two response members any test in E2-09 names. Everything
# else the answer carries is looked for by value, because the ticket settles what
# is in the answer and leaves its schema to the implementer; these two were a
# genuine gap in the ticket and were settled by the ruling of 2026-09-01.
COURSE_WEEK_FIELD = "course_week"
TERM_WEEK_FIELD = "term_week"

# The student-session dependency, shared with E2-08. It reads the session,
# refuses a role that is not `LandingRole.STUDENT` and an absent or invalid
# session with the same answer, and returns the verified claims.
DEPS_MODULE = "app.api.deps"
REQUIRE_STUDENT = "require_student"

# What that refusal looks like on the wire.
REFUSED_STATUS = 401
AUTHENTICATE_HEADER = "WWW-Authenticate"
AUTHENTICATE_SCHEME = "Bearer"
DETAIL_MEMBER = "detail"

# The copy registry, also shared with E2-08: a package whose `__init__` defines
# the frozen `CopyEntry(key, text)` and `copy_modules()`, and nothing else. This
# path's user-facing strings live in one module of it, and the refusal detail
# above is one of them.
COPY_PACKAGE = "app.copy"
COPY_STUDENT_READ_MODULE = "app.copy.student_read"
COPY_ENTRY_CLASS = "CopyEntry"
COPY_MODULES_FUNCTION = "copy_modules"
COPY_KEY_MEMBER = "key"
COPY_TEXT_MEMBER = "text"
NOT_A_STUDENT_KEY = "student.not_a_student"

# Where a landing hands the browser its session (E1-08's interface ruling), and
# the two segments this file lands on. Spelled here rather than reached for,
# because what these fixtures need is a *student* session and an *instructor*
# one, and a helper that accepted any segment would hand back a session for
# whichever view the door happened to choose.
SESSION_FRAGMENT = "#session="
STUDENT_LANDING = f"/app/student{SESSION_FRAGMENT}"
INSTRUCTOR_LANDING = f"/app/instructor{SESSION_FRAGMENT}"

# ---------------------------------------------------------------------------
# The tables and columns this file writes. Every name is somebody else's
# settled design, and each is a constant so a deliberate rename is one line.
# ---------------------------------------------------------------------------

# E2-05's four survey tables, spelled as `tests/integration/test_survey_schema.py`
# spells them. That module carries its own copy because it *is* E2-05's
# assertion about them; this one is a fixture and may not edit it, so the two
# copies are deliberate and each says so.
QUESTION_SET_TABLE = "question_set"
QUESTION_TABLE = "question"
RESPONSE_TABLE = "response"
ANSWER_TABLE = "answer"

VERSION_COLUMN = "version"
POSITION_COLUMN = "position"
RESPONSE_USER_COLUMN = "user_id"
RESPONSE_SECTION_COLUMN = "section_id"
RESPONSE_WEEK_COLUMN = "week_id"

# E2-16's addition, spelled as `survey_window` spells the column that carries the
# same rule — `WINDOW_TERM_COLUMN`, imported above from
# `fixtures/survey_windows.py`. Named separately rather than reusing that
# constant because it is a column on a different table: they agree today and a
# rename of one is not a rename of the other.
RESPONSE_TERM_COLUMN = "term_id"

FIRST_SUBMITTED_COLUMN = "first_submitted_at"
LAST_SUBMITTED_COLUMN = "last_submitted_at"
ANSWER_RESPONSE_COLUMN = "response_id"
ANSWER_QUESTION_COLUMN = "question_id"
COMMENT_TEXT_COLUMN = "comment_text"
WORKLOAD_HOURS_COLUMN = "workload_hours"

# Where a question's own wording is stored. **E2-05 does not spell this column
# anywhere a test can read** — its schema module names the ordinal, the
# conditional rule and the numeric bounds and stops — so it is discovered from
# this list rather than guessed at once. SPEC §3.2 requires the wording to be
# stored ("Question text is stored in a versioned `question_set` table"), so a
# table carrying none of these names is a named failure here and a one-line fix.
QUESTION_TEXT_COLUMNS = ("text", "prompt", "question_text", "wording", "body", "label")

# The version the shipped set carries. SPEC §3.2's own number, not this file's:
# "the five questions (standardized, v1 fixed)". Deliberately the only set these
# fixtures seed, so that no test here depends on how an implementation chooses
# among several — which version a form serves is a question E2-09 leaves open.
SHIPPED_QUESTION_SET_VERSION = 1

# ---------------------------------------------------------------------------
# The calendar this world stands on.
# ---------------------------------------------------------------------------

# The term week both cohorts below are live in, and neither one begins in. Both
# run to the end of the term, so any week from 7 to 18 would satisfy the first
# half; 13 is chosen for the second half — it is the section's tenth course week
# and its thirteenth term week, two numbers far enough apart that no wrong answer
# for one of them is the right answer for the other. It is also comfortably after
# the daylight-saving boundary that makes term week 11 the interesting one for
# E2-06, so nothing here turns on that.
TERM_WEEK = 13

# SPEC §2.2's start letters, from `SEEDED_COHORTS`: `D` runs fifteen weeks from
# term week 4 and `Q` runs twelve from term week 7, so term week 13 is inside both
# and is each section's *tenth* and *seventh* course week respectively. Two
# cohorts rather than one section twice, because E0-06 makes a start position
# unique within a term.
#
# **Neither cohort starts in term week 13, and that is the whole point of the
# pair.** A section whose window is over its own first week has a course week of
# 1 and a term week of 13, which distinguishes the two fields — but it does not
# distinguish a correct `course_week` from a hard-coded one. The enrolled
# section's window is over its tenth course week and its thirteenth term week, so
# every wrong answer is a different number: the term week served in the course
# week's place is 13, the offset without §2.2's inclusive `+ 1` is 9, and a
# constant is 1.
ENROLLED_COHORT = "D"
UNENROLLED_COHORT = "Q"

# The term week each of them begins in, transcribed from `SEEDED_COHORTS` — which
# is itself transcribed from `scripts/seed.py` and checked against its own dates
# by `tests/unit/test_the_fall_2026_window_calendar_is_spec_3_1s_rhythm.py`.
ENROLLED_FIRST_TERM_WEEK = SEEDED_COHORTS[ENROLLED_COHORT][1]

# Term week 13's window, out of E2-06's hand-written table. Nothing here computes
# it: a fixture that re-derived SPEC §3.1's Friday-to-Sunday rhythm would agree
# with an implementation that made the same mistake (`docs/MISTAKES.md` entry 19).
WINDOW_OPENS_AT, WINDOW_CLOSES_AT = WINDOWS_BY_TERM_WEEK[TERM_WEEK]

# Three instants for the development clock to pretend, one on each side of that
# window and one inside it. Whole days away from either edge, because ADR 0109
# makes the effective instant `real + (pretend_now - anchored_at)` — it keeps
# moving while it is read, so a value placed a second from an edge is a boundary
# nothing can stand on. The exact-boundary semantics are E2-06's, asserted
# through `open_window_for_section`'s own `at` parameter, and are not reopened
# here. Their order against the window is asserted by the test that uses them.
INSIDE_THE_WINDOW = datetime(2026, 11, 14, 12, 0, tzinfo=UTC)
BEFORE_THE_WINDOW = datetime(2026, 11, 12, 12, 0, tzinfo=UTC)
AFTER_THE_WINDOW = datetime(2026, 11, 17, 12, 0, tzinfo=UTC)

# What the enrolled section's open window is the tenth week *of*. **Written out
# rather than computed**, and then checked against the cohort facts by the test
# that uses it: an expectation derived by the same arithmetic as the code under
# test agrees with an implementation that made the same mistake
# (`docs/MISTAKES.md` entry 19). The guard beside it is what stops the literal
# going stale if the cohort above ever changes — term week 13 of a section that
# began in term week 4 is its tenth week, counting the first week as week 1,
# which is how §2.2 numbers a course week.
EXPECTED_COURSE_WEEK = 10
EXPECTED_TERM_WEEK = 13

# When the student and the classmate first appear on the roster: the day the
# enrolled section begins, comfortably before every instant these fixtures ever
# pretend — and `ended_on` is `None`, the open window a roster sync leaves on a
# member it is still seeing (ADR 0020).
ENROLLED_SINCE: date = SEEDED_COHORTS[ENROLLED_COHORT][2]

# And when the third person appears on the other section's roster: that section's
# own first day, which is later and is still before every pretended instant. Their
# enrollment has to be **live** at the moment a test reads, or a read that dropped
# its student predicate would filter the row out on the liveness test instead and
# the mutation would survive for a second reason.
OTHER_SECTION_ENROLLED_SINCE: date = SEEDED_COHORTS[UNENROLLED_COHORT][2]

# When a submission was made: inside the window, an hour before the instant the
# reads are taken at. E2-05 puts no server default on either column, so both are
# written here.
SUBMITTED_AT = datetime(2026, 11, 14, 11, 0, tzinfo=UTC)

# ---------------------------------------------------------------------------
# FIX-01 item 4 — the *next* window, for a section whose survey is not open.
# ---------------------------------------------------------------------------

# Two more term weeks out of the same hand-written table, for the case a section
# is closed and has a window still to come. Both are inside both seeded cohorts'
# spans — `D` runs term weeks 4 to 18 and `Q` runs 7 to 18 — and both open after
# `AFTER_THE_WINDOW`, so at that instant term week 13's window has closed and
# each of these is still ahead.
#
# **They are two different weeks on purpose, and the other section's is the
# earlier of the two.** The reader's own next window is term week 15; the section
# they are *not* enrolled in gets term week 14. So a read that asks "which window
# opens next" without saying whose section it is asking about answers the other
# one's instant — the ordinary shape of that mutation, since a query ordered by
# `opens_at` takes the earliest row it can see. Were the reader's the earlier of
# the pair, the same mutation would return the correct answer and survive with the
# suite green (`docs/MISTAKES.md` entry 3).
NEXT_TERM_WEEK = 15
OTHER_SECTIONS_NEXT_TERM_WEEK = 14
NEXT_WINDOW_OPENS_AT, NEXT_WINDOW_CLOSES_AT = WINDOWS_BY_TERM_WEEK[NEXT_TERM_WEEK]
OTHER_NEXT_WINDOW_OPENS_AT, OTHER_NEXT_WINDOW_CLOSES_AT = WINDOWS_BY_TERM_WEEK[
    OTHER_SECTIONS_NEXT_TERM_WEEK
]

# The two members FIX-01 adds to the read answer, spelled exactly as the work
# order settles them. `next_window_opens_at` rides the enrolled-section entry and
# is non-null only when that section's survey is closed and a materialized window
# still lies ahead of it; `institution_timezone` is deployment configuration —
# the zone SPEC §3.1 puts every window's wall-clock time in — and the screen
# renders the instant in it.
NEXT_WINDOW_FIELD = "next_window_opens_at"
INSTITUTION_TIMEZONE_FIELD = "institution_timezone"

# The two zones the timezone member is measured under. **Both are stated rather
# than one being inherited** (`docs/MISTAKES.md` entry 40): a test that asserted
# only the documented default would pass against a member hard-coded to it, which
# is the mutation this pair exists to kill. `Pacific/Honolulu` is a valid IANA
# name, is nothing this repository configures anywhere, and has no daylight
# saving — so a green under it cannot be a coincidence of offsets.
DEFAULT_INSTITUTION_TIMEZONE = "America/New_York"
A_NON_DEFAULT_INSTITUTION_TIMEZONE = "Pacific/Honolulu"

# ---------------------------------------------------------------------------
# What is written into the rows a test then looks for.
# ---------------------------------------------------------------------------

# SPEC §3.2's five questions, in its own order, worded by this file rather than
# quoted from the spec. **Not the spec's wording, deliberately**: the shipped
# text is `scripts/seed.py`'s and this database is not seeded by it, so what a
# read path must return is whatever is stored — and a needle nobody could produce
# by accident is what makes "the form's questions came back" a measurement
# rather than a coincidence.
QUESTION_PROMPTS = (
    "E2-09 seeded prompt 1 of 5: this week my instructor supported my learning",
    "E2-09 seeded prompt 2 of 5: what would you say about the instructor",
    "E2-09 seeded prompt 3 of 5: this week the materials supported my learning",
    "E2-09 seeded prompt 4 of 5: what would you say about the course",
    "E2-09 seeded prompt 5 of 5: hours spent on this course this week",
)

# The student's own answers, and a classmate's. Distinct in both currencies a
# leak could travel in: a string and a number. The workload figures are legal
# against SPEC §3.2's 0-40 range in half-hour steps, and neither is a substring
# of the other — a scan for `6.5` would find it inside `16.5`, and a needle that
# can be found inside the value it is supposed to be unlike is a red nobody can
# act on.
#
# **They are compared as substrings of what is stored, in both directions**,
# because the column's scale is E2-05's and not this file's: a `numeric(4, 2)`
# renders 7.5 as `7.50`, so an equality test between the value written here and
# the value read back would fail inside a test's own canary rather than on its
# subject.
OWN_COMMENT = "E2-09 own comment: the pacing in week 13 was too fast for me"
OWN_WORKLOAD = Decimal("7.5")
CLASSMATE_COMMENT = "E2-09 classmate comment: I have never understood the readings"
CLASSMATE_WORKLOAD = Decimal("13.5")

# And the third person's, submitted in the section the reader is **not** enrolled
# in. **This pair is the mutation battery's finding written as data.** A read that
# has lost `Enrollment.user_id == user_id` returns every live enrollment there is;
# unless somebody is enrolled in the other section, every one of those is still
# the reader's own section and the widened read is indistinguishable from the
# correct one. These are the values that come back when it is not.
#
# `21.5` shares no digits-and-point run with `7.5` or `13.5`, so no one of the
# three can be found inside another.
OTHER_SECTION_COMMENT = "E2-09 other-section comment: the group work never got organised"
OTHER_SECTION_WORKLOAD = Decimal("21.5")

# The shortest stored string these fixtures will hand a test as something to
# search a response for. A section code is four characters (`61WW`), which is the
# floor; anything shorter is found inside half the strings a correct JSON body
# contains and would make a scan red against every implementation.
SHORTEST_TELLING_VALUE = 4

# ---------------------------------------------------------------------------
# E2-17 item 5 — the course label the read answer gains, respelled by FIX-01.
# ---------------------------------------------------------------------------

# The three tables above `section` that the label is built out of, and the
# columns they hold it in. `lms_number` and `lms_title` are E0-05's names,
# spelled the same way `tests/fixtures/provisioning.py` and
# `test_demo_seed_script.py` spell them; `term.name` is E0-06's, and it is
# `String(100) NOT NULL` so a label built from it can never carry a hole. The
# prefix's own code is looked for among candidates rather than named, the way
# `tests/fixtures/provisioning.py::PREFIX_CODE_COLUMNS` does, because no ticket
# in E2 settles that column and a guess here would fail inside a fixture.
COURSE_TABLE = "course"
PREFIX_TABLE = "prefix"
COURSE_NUMBER_COLUMN = "lms_number"
COURSE_TITLE_COLUMN = "lms_title"
TERM_NAME_COLUMN = "name"
PREFIX_CODE_COLUMNS = ("code", "prefix_code", "name")

# The field E2-17 item 5 added to the read answer, and the shape FIX-01 item 2
# respells its value into. **Both are the ticket's, transcribed once**: the
# member stays `course_label`, and the owner's ruling of 2026-09-03 fixes the
# value as `<prefix code> <lms_number> <section code> — <lms_title>, <term
# name>`, e.g. `MATH 140 E1FF — College Algebra, Fall 2026`. The order is the
# ruling's own: "prefix, number, then section code, then the em-dash title, then
# the term's name".
#
# Nothing here re-derives any of it from the code that will produce it
# (`docs/MISTAKES.md` entry 19); a test module builds its expectation out of the
# rows it seeded and this spelling, and this function is the one place either
# lives (`docs/MISTAKES.md` entry 13 — three modules ask for this label).
COURSE_LABEL_FIELD = "course_label"
COURSE_LABEL_SEPARATOR = "—"
COURSE_LABEL_TERM_SEPARATOR = ","


def course_label(code: str, number: str, section_code: str, title: str, term_name: str) -> str:
    """FIX-01 item 2's label, composed from one section's own five values."""
    return (
        f"{code} {number} {section_code} {COURSE_LABEL_SEPARATOR} "
        f"{title}{COURSE_LABEL_TERM_SEPARATOR} {term_name}"
    )


# A prefix, a course and a section of them that this student is **not** enrolled
# in — the rows a widened join reaches and a correctly scoped read cannot.
#
# **The world's two sibling sections cannot serve for this.** `Fall2026` seeds
# both of them under one containment chain on purpose, so they share a course and
# therefore share a course label: an answer that named the *other* section's
# course would carry exactly the string a correct answer carries, and a scan over
# it would be silent (`docs/MISTAKES.md` entry 3). The course below is the one
# whose label is nobody's but its own.
#
# **Every needle here is chosen so it cannot be found by accident.** `ZQXK` is
# four upper-case letters, none of them a hexadecimal digit, so it cannot occur
# inside a uuid the answer legitimately carries; the title is a sentence nothing
# else in this project says. The number is three digits and is deliberately
# *never* searched for on its own — `742` occurs inside uuids constantly — only
# as part of the composed label.
FOREIGN_PREFIX_CODE = "ZQXK"
FOREIGN_COURSE_NUMBER = "742"
FOREIGN_COURSE_TITLE = "E2-17 unenrolled course: no student read path may name this one"
FOREIGN_SECTION_CODE = "K1WW"


class ForeignCourse(NamedTuple):
    """The prefix, course, section and window of a course the reader is not in."""

    prefix: Any
    course: Any
    section: Any
    window: Any


class StudentReadContract(NamedTuple):
    """Every name E2-09's work order settles, handed to a test module.

    A fixture rather than an import, for the reason every other fixtures module
    here gives: importing a fixtures module by name depends on where pytest put
    `tests/` on `sys.path`, and an import error is not a red.
    """

    path: str
    deps_module: str
    require_student: str
    refused_status: int
    authenticate_header: str
    authenticate_scheme: str
    detail_member: str
    copy_package: str
    copy_student_read_module: str
    copy_entry_class: str
    copy_modules_function: str
    not_a_student_key: str


@pytest.fixture
def student_read_contract() -> StudentReadContract:
    """The names E2-09 settles. See `StudentReadContract` and this module's docstring."""
    return StudentReadContract(
        path=STUDENT_READ_PATH,
        deps_module=DEPS_MODULE,
        require_student=REQUIRE_STUDENT,
        refused_status=REFUSED_STATUS,
        authenticate_header=AUTHENTICATE_HEADER,
        authenticate_scheme=AUTHENTICATE_SCHEME,
        detail_member=DETAIL_MEMBER,
        copy_package=COPY_PACKAGE,
        copy_student_read_module=COPY_STUDENT_READ_MODULE,
        copy_entry_class=COPY_ENTRY_CLASS,
        copy_modules_function=COPY_MODULES_FUNCTION,
        not_a_student_key=NOT_A_STUDENT_KEY,
    )


@pytest.fixture
def require_student_dependency() -> Any:
    """`app.api.deps.require_student`, or a failure naming the symbol E2-09 owes.

    The same shape as `tests/fixtures/survey_windows.py`'s `survey_window_service`
    and for the same reason: a `ModuleNotFoundError` at collection time is a
    broken run, and a named failure inside a test is a red that says which
    deliverable is absent.
    """
    try:
        module = import_module(DEPS_MODULE)
    except ModuleNotFoundError as missing:  # pragma: no cover - a red, not a branch
        pytest.fail(
            f"`{DEPS_MODULE}` does not import ({missing}). E1-13 already puts this project's door "
            "pages there, and E2-09 adds the student-session dependency beside them."
        )
    dependency = getattr(module, REQUIRE_STUDENT, None)
    if not callable(dependency):
        pytest.fail(
            f"`{DEPS_MODULE}` exposes no callable `{REQUIRE_STUDENT}`; it exposes "
            f"{sorted(name for name in vars(module) if not name.startswith('_'))}.\n\n"
            "E2-09's work order settles it as the shared student-session dependency: it reads the "
            "session through `app.services.session`, refuses any role that is not "
            f"`LandingRole.STUDENT` and any absent or invalid session with the same {REFUSED_STATUS}"
            f", and returns the verified claims. It is also what the inventory of student-visible "
            "routes is derived from — a route table with no such dependency on it is an inventory "
            "with nothing in it, which is the state SPEC §4.1 item 1 has been waiting in since E0."
        )
    return dependency


class CopyRegistry(NamedTuple):
    """The copy package, and every `CopyEntry` reachable through `copy_modules()`."""

    package: ModuleType
    modules: tuple[ModuleType, ...]
    entries: dict[str, str]


def copy_entries_in(module: Any, entry_class: Any) -> dict[str, str]:
    """Every `CopyEntry` a module holds, by key, however it holds them.

    Module-level names, and the members of any list, tuple, set or dict of them —
    because E2-09's work order settles the *shape of an entry* and deliberately
    settles no central list, so how a module presents its entries is the
    implementer's to choose and a reader that demanded one spelling would be
    choosing it for them.
    """
    found: dict[str, str] = {}

    def collect(value: Any) -> None:
        if isinstance(value, entry_class):
            key = getattr(value, COPY_KEY_MEMBER, None)
            text = getattr(value, COPY_TEXT_MEMBER, None)
            if isinstance(key, str) and isinstance(text, str):
                found[key] = text
            return
        if isinstance(value, dict):
            for item in value.values():
                collect(item)
            return
        if isinstance(value, list | tuple | set | frozenset):
            for item in value:
                collect(item)

    for name, value in vars(module).items():
        if not name.startswith("_"):
            collect(value)
    return found


@pytest.fixture
def copy_registry() -> CopyRegistry:
    """The `app.copy` package as E2-08 and E2-09 both settle it, read once.

    Fails by name rather than by import error for the reason
    `require_student_dependency` gives above.
    """
    try:
        package = import_module(COPY_PACKAGE)
    except ModuleNotFoundError as missing:  # pragma: no cover - a red, not a branch
        pytest.fail(
            f"`{COPY_PACKAGE}` does not import ({missing}). E2-09's work order settles it as the "
            f"package whose `__init__` defines the frozen dataclass `{COPY_ENTRY_CLASS}(key, text)`"
            f" and `{COPY_MODULES_FUNCTION}()`, and nothing else — no central list. This path's "
            f"user-facing strings live in `{COPY_STUDENT_READ_MODULE}`, for E2-11 to read."
        )
    entry_class = getattr(package, COPY_ENTRY_CLASS, None)
    modules_function = getattr(package, COPY_MODULES_FUNCTION, None)
    if not isinstance(entry_class, type) or not callable(modules_function):
        pytest.fail(
            f"`{COPY_PACKAGE}` exposes `{COPY_ENTRY_CLASS}`={entry_class!r} and "
            f"`{COPY_MODULES_FUNCTION}`={modules_function!r}; it exposes "
            f"{sorted(name for name in vars(package) if not name.startswith('_'))}. Both are the "
            "shared contract E2-08 and E2-09 build against, so a divergence is a dispute rather "
            "than a rename."
        )
    modules = tuple(modules_function())
    entries: dict[str, str] = {}
    for module in modules:
        entries.update(copy_entries_in(module, entry_class))
    return CopyRegistry(package=package, modules=modules, entries=entries)


# ---------------------------------------------------------------------------
# The world: one student, two sibling sections, one of them theirs.
# ---------------------------------------------------------------------------


def key_of(tables: dict[str, Any], table_name: str, row: Any) -> Any:
    """One seeded row's primary key (ADR 0016 makes every key a single uuid)."""
    return row[single_primary_key(require_table(tables, table_name))]


def telling_values(row: Any) -> set[str]:
    """Every value on a row, in the spellings a response could carry it in.

    A uuid is taken both hyphenated and hyphen-stripped: `str(...)` is what
    anything rendering one produces by default and `uuid.hex` is the near miss
    that walks through a search for the first — the pair
    `tests/integration/test_the_dev_console_names_nobody.py` had to add after a
    mutation battery walked past it.

    Non-string, non-uuid values are left out, and that is a disclosed limit
    rather than an oversight: the two sections here carry windows over the same
    term week, so their instants and their week number are *equal* and a scan
    over them could not tell one section's from the other's. What distinguishes
    section B is its own identifiers, and those are strings and uuids.
    """
    found: set[str] = set()
    for value in dict(row).values():
        if isinstance(value, UUID):
            written = str(value)
            found.update({written, written.replace("-", "")})
        elif isinstance(value, str) and len(value) >= SHORTEST_TELLING_VALUE:
            found.add(value)
    return found


class StudentReadWorld:
    """The rows a student's read path answers over, and what a test may look for.

    Seeded committed and removed by `committed_rows`' diff-delete at teardown.
    """

    def __init__(self, rows: Any, tables: dict[str, Any]) -> None:
        self.rows = rows
        self.tables = tables
        self.user_id: Any = None
        self.subject: str = ""
        self.classmate_id: Any = None
        self.other_section_student_id: Any = None
        self.enrolled_enrollment: Any = None
        self.other_enrollment: Any = None
        self.other_section_response: Any = None
        self.term: Any = None
        self.week: Any = None
        self.enrolled_section: Any = None
        self.other_section: Any = None
        self.enrolled_window: Any = None
        self.other_window: Any = None
        self.calendar: Any = None
        self.question_set: Any = None
        self.questions: list[Any] = []
        self.question_texts: list[str] = []
        self.own_response: Any = None

    # -- what a test looks for ----------------------------------------------

    @property
    def enrolled_section_id(self) -> Any:
        return key_of(self.tables, SECTION_TABLE, self.enrolled_section)

    @property
    def other_section_id(self) -> Any:
        return key_of(self.tables, SECTION_TABLE, self.other_section)

    @property
    def other_section_code(self) -> str:
        return f"{UNENROLLED_COHORT}{COHORT_SECTION_ORDINAL}{COHORT_SECTION_MODALITY}"

    def mine(self) -> set[str]:
        """Every string that belongs to the reader's own side of the two sections.

        Subtracted from the other section's values below, so that everything the
        two share — the term, the course above them, the week their windows are
        over, the containment chain — is excluded and what is left belongs to the
        other section alone. A scan built the other way would report the term
        identifier as a leak and be red against every correct answer.
        """
        return (
            telling_values(self.enrolled_section)
            | telling_values(self.enrolled_window)
            | telling_values(self.week)
            | telling_values(self.term)
            | telling_values(self.enrolled_enrollment)
        )

    def anything_shaped_like_the_other_sections_student(self) -> set[str]:
        """The rows that reach the answer only if the read stops filtering by student.

        **The mutation battery's finding, as a set of values.** The section, the
        window and the code below are reachable by a read widened to the course,
        the term or the week; *these* are reachable by a read that dropped
        `Enrollment.user_id == user_id` and by nothing else — the third person's
        own enrollment row, and the submission they made in the other section.
        Without them that mutation returns the same rows as the correct read and
        survives every test in this ticket, which is exactly what happened.
        """
        return (
            telling_values(self.other_enrollment)
            | {OTHER_SECTION_COMMENT, str(OTHER_SECTION_WORKLOAD)}
        ) - self.mine()

    def anything_shaped_like_the_other_section(self) -> set[str]:
        """Every string that names the section this student is **not** enrolled in.

        Its own row and its window, which a widened join reaches; and the third
        person's enrollment and submission, which only a lost student predicate
        reaches. One set, because §4.1 item 1 is one rule — nothing from a section
        the student is not in — and a test that scanned for one half would be
        silent about whichever mutation produced the other.
        """
        theirs = telling_values(self.other_section) | telling_values(self.other_window)
        return {
            value for value in theirs if value not in self.mine()
        } | self.anything_shaped_like_the_other_sections_student()

    def anything_shaped_like_a_classmates_answer(self) -> set[str]:
        """The values a classmate's stored submission would put on a page."""
        return {CLASSMATE_COMMENT, str(CLASSMATE_WORKLOAD)}

    def anything_shaped_like_my_own_answer(self) -> set[str]:
        """The values this student's own stored submission would put on a page."""
        return {OWN_COMMENT, str(OWN_WORKLOAD)}

    # -- the course above a section (E2-17 item 5) ---------------------------

    def prefix_code_column(self) -> str:
        """The column a prefix's code is stored in, discovered rather than guessed.

        The same shape as `question_text_column` below and for the same reason: no
        ticket in E2 spells this column, so a fixture that named one would fail
        inside its own seeding on a schema it had guessed wrong. The candidates are
        a constant in this module, so a deliberate rename is one line.
        """
        return require_column(require_table(self.tables, PREFIX_TABLE), PREFIX_CODE_COLUMNS)

    def parent_row(self, child_table: str, parent_table: str, row: Any) -> Any:
        """The `parent_table` row that `row` points at, followed through its foreign key.

        Followed rather than assumed: `section.course_id` and `course.prefix_id`
        are almost certainly spelled that way, and "almost certainly" is how a
        fixture ends up reading `None` and answering that a course has no prefix
        (`tests/fixtures/provisioning.py::ProvisionedRows.link` says the same).
        """
        columns = foreign_key_columns(require_table(self.tables, child_table), parent_table)
        if len(columns) != 1:
            pytest.fail(
                f"`{child_table}` has {len(columns)} foreign keys into `{parent_table}` "
                f"({columns}); this fixture needs exactly one to walk from a section up to the "
                "course whose label E2-17 item 5 puts on the page."
            )
        table = require_table(self.tables, parent_table)
        key = single_primary_key(table)
        # The same rollback `stored_answer_values` takes, and for the same reason:
        # this session has been idle across HTTP calls made on another connection,
        # and a read taken inside a stale snapshot answers about a database that
        # has moved.
        self.rows.session.rollback()
        found = (
            self.rows.session.execute(table.select().where(table.c[key] == row[columns[0]]))
            .mappings()
            .one_or_none()
        )
        if found is None:
            pytest.fail(
                f"The `{child_table}` row names a `{parent_table}` "
                f"({row[columns[0]]}) that is not in the table. The containment chain this world "
                "seeds runs institution → college → department → prefix → course → section, so a "
                "miss here means the row was seeded against a chain that no longer exists."
            )
        return found

    def course_label_of(self, section: Any) -> str:
        """FIX-01 item 2's label for one section, built from the seeded rows.

        **The values come from the database and the spelling from the ticket.** An
        expectation read out of the code that produces it agrees with an
        implementation that got it wrong (`docs/MISTAKES.md` entry 19), and one
        invented here would be this fixture choosing what the label says.

        **The term is followed out of the section's own row rather than taken
        from `self.term`.** The two agree in this world — everything here is
        seeded under one Fall 2026 term — and that is exactly why reading the
        convenient one would be untestable: a label that named *a* term rather
        than *this section's* term would compose identically. `parent_row`
        follows `section.term_id`, so the value is the one the read path has to
        reach for as well.
        """
        course = self.parent_row(SECTION_TABLE, COURSE_TABLE, section)
        prefix = self.parent_row(COURSE_TABLE, PREFIX_TABLE, course)
        term = self.parent_row(SECTION_TABLE, TERM_TABLE, section)
        return course_label(
            prefix[self.prefix_code_column()],
            course[COURSE_NUMBER_COLUMN],
            section[SECTION_CODE_COLUMN],
            course[COURSE_TITLE_COLUMN],
            term[TERM_NAME_COLUMN],
        )

    def anything_shaped_like_the_foreign_courses_label(self, foreign: ForeignCourse) -> set[str]:
        """Every string that names a course this student is not enrolled in.

        The composed label, the prefix code and the title — and **not** the course
        number, which is three digits and occurs inside uuids the answer carries
        legitimately. A needle that can be found inside a value it is meant to be
        unlike is a red nobody can act on (this module's own note beside
        `OWN_WORKLOAD`).
        """
        return {
            self.course_label_of(foreign.section),
            FOREIGN_PREFIX_CODE,
            FOREIGN_COURSE_TITLE,
        }

    # -- seeding -------------------------------------------------------------

    def build(self, *, subject: str) -> "StudentReadWorld":
        """Seed the whole world, committed, and answer it.

        The order is the order the schema requires: the term and its weeks, then
        the two sections of it, then a window each, then the question set, then
        the people and the one enrollment that makes exactly one of those two
        sections this student's.
        """
        self.subject = subject

        calendar = Fall2026(self.rows.seed, self.rows.session, self.tables).build()
        # Kept, so a test that needs a window over some *other* term week has the
        # `week` rows to hang it on. `seed_window_over` is the only reader.
        self.calendar = calendar
        self.term = calendar.term
        self.week = calendar.weeks[TERM_WEEK]
        self.enrolled_section = calendar.section_row(ENROLLED_COHORT)
        self.other_section = calendar.section_row(UNENROLLED_COHORT)
        self.enrolled_window = self.seed_window(self.enrolled_section)
        self.other_window = self.seed_window(self.other_section)
        self.seed_questions()
        self.rows.commit()
        return self

    def seed_window(self, section: Any) -> Any:
        """One `survey_window` over term week 13 for one section, uncommitted.

        The world's own window, seeded during `build` and committed with the rest
        of it. Delegates so that "how a window row is written" has one spelling
        here rather than two (`docs/MISTAKES.md` entry 13).
        """
        return self.seed_window_over(section, TERM_WEEK, commit=False)

    def seed_window_over(self, section: Any, term_week: int, *, commit: bool = True) -> Any:
        """One `survey_window` over any of this term's weeks, for one section.

        Written directly rather than derived through
        `app.services.survey_windows.derive_windows_for_section`, and that is
        deliberate: this ticket's subject is what a read path answers over the
        rows that exist, and routing the fixture through E2-06's derivation would
        make every assertion here rest on that service being right as well — a
        red would then name the wrong ticket. The instants are E2-06's own
        hand-written table, so the rows are the ones a correct derivation writes.

        `commit` defaults to true because every caller outside `build` is a test
        adding a window to a world that is already committed, and the tool reads
        on its own connection.
        """
        opens_at, closes_at = WINDOWS_BY_TERM_WEEK[term_week]
        window = self.rows.seed(
            SURVEY_WINDOW_TABLE,
            {},
            **{
                WINDOW_SECTION_COLUMN: key_of(self.tables, SECTION_TABLE, section),
                WINDOW_WEEK_COLUMN: key_of(self.tables, WEEK_TABLE, self.calendar.weeks[term_week]),
                WINDOW_TERM_COLUMN: key_of(self.tables, TERM_TABLE, self.term),
                WINDOW_OPENS_COLUMN: opens_at,
                WINDOW_CLOSES_COLUMN: closes_at,
            },
        )
        if commit:
            self.rows.commit()
        return window

    def seed_a_course_this_student_is_not_in(self) -> ForeignCourse:
        """A prefix, a course, a section of them and a window over this world's week.

        **Under this world's own term and under nothing else of it.** The term is
        handed to the chain so the window's composite key holds; the prefix, the
        course and everything above them are this call's own, so the section that
        comes out shares no course with either of the two the world already has.
        That is the whole point of it: `Fall2026` puts both sibling sections under
        one course, so their *labels* are identical and neither can serve as a
        needle for the other (E2-17 item 5).

        The section's calendar is the enrolled cohort's, written out rather than
        invented by the seeding walker. Not decoration: a test may enrol somebody
        in this section, and a section whose `start_date` and `length_weeks` are a
        fixture's arbitrary pair makes SPEC §2.2's course-week arithmetic answer
        something nobody can read.

        Committed, because the tool reads on its own connection.
        """
        chain: dict[str, Any] = {TERM_TABLE: self.term}
        prefix = self.rows.seed(
            PREFIX_TABLE, chain, **{self.prefix_code_column(): FOREIGN_PREFIX_CODE}
        )
        chain[PREFIX_TABLE] = prefix
        course = self.rows.seed(
            COURSE_TABLE,
            chain,
            **{
                COURSE_NUMBER_COLUMN: FOREIGN_COURSE_NUMBER,
                COURSE_TITLE_COLUMN: FOREIGN_COURSE_TITLE,
            },
        )
        chain[COURSE_TABLE] = course
        length_weeks, _first_term_week, start = SEEDED_COHORTS[ENROLLED_COHORT]
        section = self.rows.seed(
            SECTION_TABLE,
            chain,
            **{
                SECTION_CODE_COLUMN: FOREIGN_SECTION_CODE,
                SECTION_LENGTH_COLUMN: length_weeks,
                SECTION_START_COLUMN: start,
                SECTION_END_COLUMN: start + timedelta(days=length_weeks * 7 - 1),
            },
        )
        window = self.seed_window(section)
        self.rows.commit()
        return ForeignCourse(prefix=prefix, course=course, section=section, window=window)

    def question_text_column(self) -> str:
        """The column a question's own wording is stored in, discovered not guessed."""
        table = require_table(self.tables, QUESTION_TABLE)
        for candidate in QUESTION_TEXT_COLUMNS:
            if candidate in table.c:
                return candidate
        pytest.fail(
            f"`{QUESTION_TABLE}` carries none of {list(QUESTION_TEXT_COLUMNS)} — it carries "
            f"{[column.name for column in table.columns]}. SPEC §3.2 stores the question text in "
            "the versioned set, and E2-09's read path has to return it or E2-10 has no form to "
            "render. The candidate list is a constant in tests/fixtures/student_read.py, so a "
            "column named some other way is a one-line change here."
        )

    def seed_questions(self) -> None:
        """SPEC §3.2's five questions, in one set at the shipped version.

        One set and only one, so that no test here depends on how an
        implementation chooses among several — which version a form serves is a
        question E2-09 leaves open, and a fixture seeding two would be deciding it.
        """
        column = self.question_text_column()
        self.question_set = self.rows.seed(
            QUESTION_SET_TABLE, {}, **{VERSION_COLUMN: SHIPPED_QUESTION_SET_VERSION}
        )
        chain = {QUESTION_SET_TABLE: self.question_set}
        limit = getattr(require_table(self.tables, QUESTION_TABLE).c[column].type, "length", None)
        for position, prompt in enumerate(QUESTION_PROMPTS, start=1):
            written = prompt if limit is None else prompt[:limit]
            self.questions.append(
                self.rows.seed(
                    QUESTION_TABLE, chain, **{POSITION_COLUMN: position, column: written}
                )
            )
        # Read back rather than remembered, so that a column narrower than these
        # prompts leaves the tests looking for what is stored (`docs/MISTAKES.md`
        # entry 30's mirror image: what is searched for must be what is there).
        self.question_texts = [row[column] for row in self.questions]

    def seed_submission(
        self, *, user_id: Any, comment: str, workload: Decimal, section_id: Any = None
    ) -> Any:
        """One whole submission — a `response` and two `answer` rows — for one person.

        Two answers rather than one because a leak travels in two currencies: a
        comment is a string and a workload is a number, and a scan that searched
        only for strings would walk past the second (the mutation that survived
        `test_the_dev_console_names_nobody.py`, one value over).

        `section_id` defaults to the reader's own section, which is where the
        classmate's submission goes; the third person's goes in the other one, and
        the caller says so rather than this method inferring it from the user.

        **The response names its term as well as its section and its week**, and
        E2-16 is why (`docs/disputes/E2-16-02.md`). That ticket gave `response`
        the term-agreement rule `survey_window` has carried since E2-05 — a
        `term_id` held by composite foreign keys into `section (id, term_id)` and
        `week (id, term_id)` — and this call names two of the three explicitly
        while handing the seeding walker an empty chain. Left to fill `term_id`
        itself the walker builds a fresh section in a fresh term and takes that
        term, and the composite key refuses the row: this method raised inside the
        `student_read_door` fixture and took fourteen tests in three modules with
        it, none of them about a term. It is `self.term` for the same reason
        `seed_window` above uses it — both sections this world seeds are of the
        one Fall 2026 term it builds, so a section from another term passed in
        here would be refused, correctly and by name.
        """
        response = self.rows.seed(
            RESPONSE_TABLE,
            {},
            **{
                RESPONSE_USER_COLUMN: user_id,
                RESPONSE_SECTION_COLUMN: (
                    self.enrolled_section_id if section_id is None else section_id
                ),
                RESPONSE_WEEK_COLUMN: key_of(self.tables, WEEK_TABLE, self.week),
                RESPONSE_TERM_COLUMN: key_of(self.tables, TERM_TABLE, self.term),
                FIRST_SUBMITTED_COLUMN: SUBMITTED_AT,
                LAST_SUBMITTED_COLUMN: SUBMITTED_AT,
            },
        )
        response_id = key_of(self.tables, RESPONSE_TABLE, response)
        for question, value in (
            (self.questions[1], {COMMENT_TEXT_COLUMN: comment}),
            (self.questions[4], {WORKLOAD_HOURS_COLUMN: workload}),
        ):
            self.rows.seed(
                ANSWER_TABLE,
                {},
                **{
                    ANSWER_RESPONSE_COLUMN: response_id,
                    ANSWER_QUESTION_COLUMN: key_of(self.tables, QUESTION_TABLE, question),
                    **value,
                },
            )
        self.rows.commit()
        return response

    def submit_own(self) -> Any:
        """This student's own submission for the open week. Called by a test, never here."""
        self.own_response = self.seed_submission(
            user_id=self.user_id, comment=OWN_COMMENT, workload=OWN_WORKLOAD
        )
        return self.own_response

    def not_stored(self, values: set[str]) -> list[str]:
        """Those of `values` that no `answer` row carries, compared as substrings.

        As substrings because the value written here and the value read back need
        not be spelled alike: E2-05 owns `workload_hours`' scale, so `7.5` may come
        back as `7.50`, and a canary comparing the two for equality would fail
        inside a test's own guard rather than on its subject. Substring
        containment also errs in the safe direction for the denial that uses it —
        it reports a value as stored whenever anything stored contains it.
        """
        stored = self.stored_answer_values()
        return sorted(value for value in values if not any(value in row for row in stored))

    def stored_answer_values(self) -> set[str]:
        """Every answer value in the database right now, read back rather than remembered.

        The canary for the two denial tests: a scan for a classmate's comment
        means nothing unless the comment is demonstrably stored where the read
        path's own connection could reach it.
        """
        table = require_table(self.tables, ANSWER_TABLE)
        self.rows.session.rollback()
        found: set[str] = set()
        for row in self.rows.session.execute(table.select()).mappings():
            for value in dict(row).values():
                if isinstance(value, str) and len(value) >= SHORTEST_TELLING_VALUE:
                    found.add(value)
                elif isinstance(value, Decimal):
                    found.add(str(value))
        return found


# ---------------------------------------------------------------------------
# The door: a real launch, a real session, and reads made with it.
# ---------------------------------------------------------------------------


def session_token_at(response: Any, landing: str, what: str) -> str:
    """The session a landing redirect carries, once it is the landing this asked for.

    **The positive control every read below rests on.** A launch that lands on
    the calm no-access page, or on some other role's route, carries no session
    this test could read as that person — and a scan of a refusal names nobody
    either (`docs/MISTAKES.md` entry 3). So the segment is checked here rather
    than anywhere later.
    """
    assert response.status_code in (302, 303, 307), (
        f"{what} answered {response.status_code} rather than the redirect E1-08's door issues for "
        f"a launch that verified. Body begins {response.text[:400]!r}."
    )
    location = response.headers.get("location") or ""
    assert location.startswith(landing), (
        f"{what} redirected to {location!r}, which does not begin `{landing}`. E1-13 resolves the "
        "landing from the launching person's own live rows, so a launch that lands anywhere else "
        "means the rows this fixture seeded are not the rows that door read — and every read made "
        "with the session it did not issue would be about somebody else."
    )
    token = location[len(landing) :]
    assert token, f"{what} redirected to {location!r}, whose `session=` fragment is empty."
    return token


class StudentReadDoor:
    """One tool, one student session, and reads of the student read path through it.

    Both E2-09 modules drive the same three things — a read as the student, a
    read as somebody who is not one, and a read with no session at all — so the
    driving lives here and each module asserts (`docs/MISTAKES.md` entry 13).
    """

    def __init__(
        self,
        driver: Any,
        world: StudentReadWorld,
        overrides: Any,
        token: str,
        instructor: Callable[[], str],
    ) -> None:
        self.driver = driver
        self.tool = driver.tool
        self.world = world
        self.overrides = overrides
        self.token = token
        self._instructor = instructor
        self._instructor_token: str | None = None

    @property
    def application(self) -> Any:
        """The FastAPI application this tool is serving, for the route-table sweep."""
        return self.tool.app

    def pretend(self, instant: datetime) -> None:
        """Move the development clock to `instant`, committed, as `POST /dev/clock` does.

        `anchored_at` is the real instant this was set at, which is what ADR 0109
        makes the offset out of. The caller names the instant: which side of a
        window the clock is on is the whole of what several tests are about.
        """
        self.overrides.set(pretend_now=instant, anchored_at=datetime.now(UTC))

    def get(self, path: str = STUDENT_READ_PATH, **params: Any) -> Any:
        """One read of `path` carrying this student's session as a Bearer token."""
        return self.tool.get(
            path,
            params=params or None,
            headers={"Authorization": f"Bearer {self.token}"},
        )

    @contextmanager
    def carrying_no_cookie(self) -> Iterator[None]:
        """Empty this client's cookie jar for the body, and put it back afterwards.

        **Without this, no request either module makes is credential-free.** E1-08
        delivers a session two ways at once — `Set-Cookie: pulse_session` on the
        landing redirect *and* the URL fragment the SPA reads — and `httpx` sends
        jar cookies on every later request to the same host, so a read made
        through the client the launch was driven with carries that student's valid
        session whether or not it carries a header. `docs/disputes/E2-09-01.md`
        measured it: the request this file called "no session at all" arrived
        carrying `pulse_session` decoding to `{"door": "LAUNCH", "role": "STUDENT",
        "sub": "mock-lms-user-learner"}`, was answered `200` with that student's
        own survey, and the test failed against a correct implementation.

        **A per-request `cookies={}` does not do it**, which is the part worth
        writing down: `httpx` merges request cookies *over* the client's jar
        rather than replacing it, so the jar's `pulse_session` is sent anyway. The
        jar has to be swapped out and restored, which is what this does.

        **Both refusal drivers use it, not only the anonymous one.** A request
        carrying an instructor's Bearer token *and* a student's cookie is refused
        for the right reason only because `session_from_request` reads Bearer
        first — a test that leaned on that precedence would be measuring the
        precedence rule rather than the role check. Emptied, each refusal carries
        exactly one credential and it is the one the method's name says.

        The student's own `get` above deliberately keeps the jar: there the cookie
        and the Bearer token are the same person's session, which is the state a
        real browser is in, and the ruling of 2026-09-01 confirms a
        cookie-delivered session is a supported path rather than a leak.
        """
        import httpx

        jar = self.tool.cookies
        self.tool.cookies = httpx.Cookies()
        try:
            yield
        finally:
            self.tool.cookies = jar

    def get_as_an_instructor(self, path: str = STUDENT_READ_PATH) -> Any:
        """The same read, carrying a session a real instructor landing issued and nothing else.

        The token is minted **before** the jar is emptied, deliberately: minting it
        drives a whole launch, and the login leg's own `state`/`nonce` cookie is
        what the launch leg is judged against — a launch driven with an emptied jar
        is refused for the handshake and this would fail in its own setup.
        """
        if self._instructor_token is None:
            self._instructor_token = self._instructor()
        with self.carrying_no_cookie():
            return self.tool.get(
                path, headers={"Authorization": f"Bearer {self._instructor_token}"}
            )

    def get_without_a_session(self, path: str = STUDENT_READ_PATH) -> Any:
        """The same read, carrying no credential of any kind — no header, and no cookie.

        Order-independent by construction: the jar is emptied whatever a previous
        call left in it, so this is an anonymous request whether or not an
        instructor launch has run first. See `carrying_no_cookie` for the incident.
        """
        with self.carrying_no_cookie():
            return self.tool.get(path)


@pytest.fixture
def student_read_door_in(
    launch_driver_in: Any,
    committed_rows: Any,
    metadata_tables: dict[str, Any],
    committed_clock_overrides: Any,
    web_identity: Any,
    enrol: Any,
    landing_ground: Any,
) -> Callable[..., StudentReadDoor]:
    """The same door, built under environment values the caller names.

    A factory beside `student_read_door` rather than instead of it, and the split
    exists for one reason: FIX-01 puts `institution_timezone` on the read answer,
    and a test that asserted only the documented default would pass against a
    member hard-coded to it. So one test asks for the door under a zone that is
    *not* the default, which means naming a setting before the application is
    imported (`docs/MISTAKES.md` entry 40) — and `tool_doors` only sees a value
    that came down through `launch_driver_in`.

    Keyword arguments are environment variable names and values, passed straight
    through. Called with none, this is exactly what `student_read_door` has always
    built.
    """

    def build(**settings: str) -> StudentReadDoor:
        return _build_student_read_door(
            launch_driver_in(**settings),
            committed_rows,
            metadata_tables,
            committed_clock_overrides,
            web_identity,
            enrol,
            landing_ground,
        )

    return build


@pytest.fixture
def student_read_door(student_read_door_in: Callable[..., StudentReadDoor]) -> StudentReadDoor:
    """A student who is enrolled in one section and not its sibling, at the door.

    Built with no environment override, so it runs under whatever `configured_env`
    laid down — the development name, which is what every test about the ordinary
    path wants. The shape `tests/fixtures/provisioning.py` gives `launch_driver`
    over `launch_driver_in`, and for the same reason.
    """
    return student_read_door_in()


def _build_student_read_door(
    launch_driver: Any,
    committed_rows: Any,
    metadata_tables: dict[str, Any],
    committed_clock_overrides: Any,
    web_identity: Any,
    enrol: Any,
    landing_ground: Any,
) -> StudentReadDoor:
    """Seed the world, enrol the people, move the clock, launch — in that order.

    Everything in order, and every step of it is somebody's existing machinery:
    the platform is registered and the launch is real (`launch_driver`), the
    subject is read off the launch the platform signs rather than copied out of
    `mock-lms/app/seed.py`, the rows are committed because the tool connects for
    itself, and the clock is moved before the launch so that the enrollment is
    judged against the day this world lives in.

    The clock starts **inside** the window, which is the state most tests want and
    none of them depends on: `pretend` moves it, and the test that is about the
    clock moves it three times.

    A module-level function rather than a fixture body, so that the two fixtures
    above share it instead of holding a copy each (`docs/MISTAKES.md` entry 13).
    """
    offer = launch_driver.offer_for_role(LEARNER_ROLE_URN)
    claims = launch_driver.claims_of(offer)
    subject = claims.get("sub")
    assert isinstance(subject, str) and subject, (
        "The learner launch this platform signs carries no `sub`, so there is no subject to seed a "
        f"`user` row for and no student to read as. The claims it signed: {sorted(claims)}."
    )

    platform_id = launch_driver.registration.platform_row[
        single_primary_key(require_table(metadata_tables, "lti_platform"))
    ]

    world = StudentReadWorld(committed_rows, metadata_tables).build(subject=subject)
    world.user_id = web_identity.user(platform_id=platform_id, subject=subject)
    world.enrolled_enrollment = enrol.enrol(
        user_id=world.user_id,
        section_id=world.enrolled_section_id,
        started_on=ENROLLED_SINCE,
        ended_on=None,
    )

    # A classmate: the same section, the same week, a submission of their own.
    # Seeded here rather than by a test because both denial tests need it and
    # neither is about how it got there — what a test decides is whether the
    # *student* has submitted anything, which is `submit_own`.
    world.classmate_id = web_identity.user(
        platform_id=platform_id, subject=f"{subject}-e2-09-classmate"
    )
    enrol.enrol(
        user_id=world.classmate_id,
        section_id=world.enrolled_section_id,
        started_on=ENROLLED_SINCE,
        ended_on=None,
    )
    world.seed_submission(
        user_id=world.classmate_id, comment=CLASSMATE_COMMENT, workload=CLASSMATE_WORKLOAD
    )

    # And somebody in the **other** section, with a submission there. Not decoration
    # and not realism for its own sake: this is the only row set a read that has
    # dropped `Enrollment.user_id == user_id` can reach and a correct read cannot.
    # Without it every live enrollment in the database is the reader's own, the
    # widened query answers exactly what the correct one answers, and the mutation
    # survives the whole ticket — which the battery measured before this person
    # existed. Their enrollment starts on their own section's first day.
    world.other_section_student_id = web_identity.user(
        platform_id=platform_id, subject=f"{subject}-e2-09-other-section"
    )
    world.other_enrollment = enrol.enrol(
        user_id=world.other_section_student_id,
        section_id=world.other_section_id,
        started_on=OTHER_SECTION_ENROLLED_SINCE,
        ended_on=None,
    )
    world.other_section_response = world.seed_submission(
        user_id=world.other_section_student_id,
        comment=OTHER_SECTION_COMMENT,
        workload=OTHER_SECTION_WORKLOAD,
        section_id=world.other_section_id,
    )

    overrides = committed_clock_overrides
    overrides.set(pretend_now=INSIDE_THE_WINDOW, anchored_at=datetime.now(UTC))

    landed, _ = launch_driver.launch(offer)
    token = session_token_at(landed, STUDENT_LANDING, "The seeded student's launch")

    def instructor_token() -> str:
        """A session a real instructor landing issued, minted only if a test asks."""
        instructor_offer = launch_driver.offer_for_role(INSTRUCTOR_ROLE_URN)
        instructor_subject = launch_driver.claims_of(instructor_offer).get("sub")
        assert isinstance(instructor_subject, str) and instructor_subject, (
            "The instructor launch this platform signs carries no `sub`, so there is no subject to "
            "seed an assignment for and no non-student session to be refused with."
        )
        landing_ground().an_instructor(platform_id=platform_id, subject=instructor_subject)
        answered, _ = launch_driver.launch(instructor_offer)
        return session_token_at(answered, INSTRUCTOR_LANDING, "The seeded instructor's launch")

    return StudentReadDoor(launch_driver, world, overrides, token, instructor_token)


# ---------------------------------------------------------------------------
# Reading an answer, without holding a copy of its schema.
# ---------------------------------------------------------------------------


def response_surface(response: Any) -> str:
    """Everything a client reading this response could see: its headers and its body.

    The headers as well as the body, because a value can ride one — a `Location`,
    a `Set-Cookie`, an `ETag` built out of the row it describes — and a scan blind
    to them reports a clean answer.
    """
    headers = " ".join(f"{name}: {value}" for name, value in response.headers.items())
    return f"{headers} {response.text}"


def decoded(response: Any, what: str) -> Any:
    """One answer's JSON, or a failure saying what came back instead.

    A decoder that quietly answered `{}` would make every assertion below it true
    of a response carrying nothing at all (`docs/MISTAKES.md` entry 3).
    """
    try:
        return json.loads(response.text)
    except ValueError as broken:
        pytest.fail(
            f"{what} answered {response.status_code} with a body that is not JSON ({broken}). It "
            f"begins {response.text[:300]!r}. E2-09's read path answers the form's question in one "
            "round trip, and a body nothing can decode answers nothing."
        )


def scalars_in(node: Any) -> list[Any]:
    """Every scalar anywhere inside a decoded JSON value, in no particular order."""
    if isinstance(node, dict):
        return [found for value in node.values() for found in scalars_in(value)]
    if isinstance(node, list):
        return [found for item in node for found in scalars_in(item)]
    return [node]


def instants_in(node: Any) -> set[datetime]:
    """Every string in a decoded answer that reads as an aware instant, as instants.

    **Spelling-independent on purpose.** E2-09 settles that the answer carries the
    window's open and close instants and settles no serialization for them, so a
    test comparing strings would be pinning a choice the ticket leaves open —
    `2026-11-13T23:00:00Z` and `2026-11-13T23:00:00+00:00` are the same moment.
    Compared as moments, either spelling passes and a wrong moment fails.
    """
    found: set[datetime] = set()
    for value in scalars_in(node):
        if not isinstance(value, str):
            continue
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            continue
        if parsed.tzinfo is not None:
            found.add(parsed)
    return found


def objects_carrying(node: Any, *names: str) -> list[dict[str, Any]]:
    """Every object anywhere in a decoded answer that carries all of `names`.

    Found by walking rather than by indexing, because E2-09 settles the two week
    *field names* and settles nothing about where in the answer they sit — one
    object per live enrollment, a list under a member, a mapping keyed by section:
    all three satisfy the ticket. A test that wrote `body["enrollments"][0]` would
    be choosing the shape; this finds the fields wherever the implementer put
    them, and a test that finds none of them says so.
    """
    found: list[dict[str, Any]] = []
    if isinstance(node, dict):
        if all(name in node for name in names):
            found.append(node)
        for value in node.values():
            found.extend(objects_carrying(value, *names))
    elif isinstance(node, list):
        for item in node:
            found.extend(objects_carrying(item, *names))
    return found


def sole_entry(body: Any, answered: Any) -> dict[str, Any]:
    """The one object in the answer that carries FIX-01's next-window member.

    One, because the reader this world builds has exactly one live enrollment.
    Nought means the member is not on the wire at all, which is the state FIX-01's
    tests are first written red against; more than one means an enrollment is
    being reported twice, which is a different defect and worth telling apart from
    a wrong instant.

    Here rather than in either test module because two of them ask the same
    question of the same answer — the ordinary read-path module and the §4.1
    denial module beside it (`docs/MISTAKES.md` entry 13).
    """
    entries = objects_carrying(body, NEXT_WINDOW_FIELD)
    assert len(entries) == 1, (
        f"{len(entries)} objects in the answer carry `{NEXT_WINDOW_FIELD}`, and this student has "
        f"one live enrollment. Body begins {answered.text[:400]!r}.\n\n"
        "FIX-01 item 4 puts the next materialized window's opening instant on the enrolled-section "
        f"entry under exactly that name, as `datetime | None` — so the member is *present* on "
        "every entry and is null when there is nothing ahead. Nought here is the member missing "
        "from the schema, which is what this ticket owes; two is one enrollment answered twice."
    )
    return entries[0]


def instant_carried(entry: dict[str, Any], answered: Any) -> datetime:
    """One entry's next-window member as a moment, or a failure saying what it was.

    Parsed rather than string-compared, for the reason `instants_in` gives above:
    FIX-01 settles the member and settles no serialization for it, so
    `2026-11-27T23:00:00Z` and `2026-11-27T23:00:00+00:00` are one moment written
    two ways and a test comparing text would be pinning a choice the ticket leaves
    open.
    """
    value = entry[NEXT_WINDOW_FIELD]
    assert isinstance(value, str), (
        f"`{NEXT_WINDOW_FIELD}` came back as {value!r} ({type(value).__name__}). It carries an "
        f"instant, and the answer is JSON. Body begins {answered.text[:400]!r}."
    )
    parsed = datetime.fromisoformat(value)
    assert parsed.tzinfo is not None, (
        f"`{NEXT_WINDOW_FIELD}` came back as {value!r}, which carries no offset. ADR 0019 stores "
        "every instant aware, and a naive one on the wire is a moment the browser will read in "
        "whatever zone it happens to be in — which is the whole defect this member exists to fix."
    )
    return parsed


def booleans_in(node: Any, path: str = "") -> dict[str, bool]:
    """Every boolean in a decoded answer, by the path it sits at.

    By path rather than by name, so that the same field of two answers is
    compared with itself: a test that collected names alone could not tell one
    enrollment's flag from another's.
    """
    found: dict[str, bool] = {}
    if isinstance(node, bool):
        found[path or "."] = node
    elif isinstance(node, dict):
        for name, value in node.items():
            found.update(booleans_in(value, f"{path}.{name}"))
    elif isinstance(node, list):
        for index, item in enumerate(node):
            found.update(booleans_in(item, f"{path}[{index}]"))
    return found


def around(surface: str, needle: str, width: int = 80) -> str:
    """The text a suspected leak sits in, so a failure can be judged in one read."""
    at = surface.find(needle)
    if at < 0:  # pragma: no cover - only reached if the caller found it another way
        return ""
    return surface[max(0, at - width) : at + len(needle) + width]
