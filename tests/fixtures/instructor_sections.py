"""E4-18 — the sections one instructor teaches, and the world that says which those are.

Two test modules ask the same three questions of the same world, so the world is
built here and each module asserts (`docs/MISTAKES.md` entry 13):

  - **An instructor who teaches two sections, and somebody else who teaches a
    third.** E4-18's list is "exactly the sections the session's person holds the
    teaching-instructor grant over", so a world with one grant per person could
    not tell a correct read from one that answered every section of the term. The
    launching instructor's first grant is `tests/fixtures/report_api.py`'s — the
    `INSTRUCTOR` assignment scoped to the taught section that `_seed_the_launching
    _person` writes — and this file adds her second and the other instructor's.

  - **A second section whose course label sorts against its section code.** The
    ticket's order is "by `course_label`, then `code`, then `section_id`", and
    every section `Fall2026` seeds sits under one course: their labels differ only
    by the code they carry in the middle, so within that world an implementation
    ordering by `code` alone and one ordering by the governed label produce the
    same list. Her second section therefore hangs off a **second course of the
    same prefix**, numbered so that the two orders disagree — see
    `HER_SECOND_COURSE_NUMBER`. Nothing here asserts the resulting order; the test
    module writes the expected order out and checks the premise first.

  - **Sessions that are not hers.** Criterion 3's two cases — a person holding no
    teaching grant, and a session naming no person — are reachable only by minting,
    because a launch that resolves to a person with no assignment does not land as
    an instructor at all (E1-13). Both are minted through `app.services.session`,
    the module both doors issue through, from a **test body** rather than from a
    fixture, so a session module that has moved is a FAILED naming it
    (`docs/MISTAKES.md` entry 44).

**The third section is a sibling of her first, under one course, and that is the
point.** `Fall2026` seeds every section it is asked for under a single containment
chain, so the section another instructor teaches differs from hers in its own row
and in nothing above it. A scope query widened to the course, the prefix, the term
or the week answers with it, and so does one that filters on the role and forgets
the person — the two mutations E4-18's scope assertion exists to kill.

**Nothing here decides what the route should answer.** This file seeds rows,
writes grants and makes requests; every expectation — the order, the entry shape,
the label — is written out in the module that asserts it (`docs/MISTAKES.md`
entries 19 and 30). The label is composed by
`tests/fixtures/student_read.py::StudentReadWorld.course_label_of`, which is the
one reader FIX-01 item 2's form has in this suite, rather than by a second copy
here.

**Which failure a red is, before E4-18 lands.** Every request goes to the route
the work order settles, over HTTP through the door E4-07's fixtures already build.
On a tree where the route is unbuilt the application answers 404, `entries_in`
fails on the status naming `ROUTE_IS_OWED`, and the refusal tests fail on the
status they compare — assertions, not errors in anybody's setup.

**The environment** (`docs/MISTAKES.md` entries 40 and 52): everything rides
`report_door`, and therefore `launch_driver_in`, `tool_doors` and `configured_env`
— the development name, laid down before the application is imported. The two
minted sessions are signed with the secret out of that same mapping rather than
out of `os.environ`, so the token this suite mints and the token the application
verifies cannot come from two readings of the environment.
"""

from collections.abc import Mapping
from datetime import timedelta
from typing import Any, NamedTuple
from uuid import UUID

import pytest

from fixtures.report_api import (
    INSTRUCTOR_ROLE,
    TAUGHT_COHORT,
    UNTAUGHT_COHORT,
    ReportDoor,
)
from fixtures.student_read import (
    AUTHENTICATE_SCHEME,
    COURSE_LABEL_FIELD,
    COURSE_NUMBER_COLUMN,
    COURSE_TABLE,
    COURSE_TITLE_COLUMN,
    PREFIX_TABLE,
    StudentReadWorld,
    decoded,
)
from fixtures.submit import session_secret
from fixtures.supervision import require_table, single_primary_key
from fixtures.survey_windows import (
    COHORT_SECTION_MODALITY,
    COHORT_SECTION_ORDINAL,
    SECTION_CODE_COLUMN,
    SECTION_END_COLUMN,
    SECTION_LENGTH_COLUMN,
    SECTION_START_COLUMN,
    SECTION_TABLE,
    SEEDED_COHORTS,
    TERM_TABLE,
)
from fixtures.web_identity import PERSON_ID_CLAIM, USER_ID_CLAIM, claims_in_session

# ---------------------------------------------------------------------------
# The names E4-18's work order and ticket settle, transcribed once.
# ---------------------------------------------------------------------------

# The route. **Settled, not discovered** — unlike E4-07's two, whose URLs no
# record named and which `tests/fixtures/report_api.py` therefore finds through
# the module: E4-18's work order fixes this path outright, and the ticket's public
# interface spells it the same way.
SECTIONS_PATH = "/instructor/sections"

# The 200 body, member by member: `{"sections": [{"section_id": …, "code": …,
# "course_label": …}]}`. `course_label` is imported rather than respelled because
# FIX-01 item 2 owns that member's name on three surfaces already, and a fourth
# copy is a fourth place for it to drift.
SECTIONS_MEMBER = "sections"
SECTION_ID_FIELD = "section_id"
CODE_FIELD = "code"
COURSE_LABEL_MEMBER = COURSE_LABEL_FIELD

# What a refusal looks like on the wire: the module's standard 401, which is
# `tests/fixtures/report_api.py`'s `ROLE_REFUSED_STATUS` and
# `tests/fixtures/student_read.py`'s `REFUSED_STATUS` before it. Imported through
# the report contract in the test modules rather than respelled here.
CACHE_CONTROL_HEADER = "Cache-Control"
NO_STORE = "no-store"

# Where the platform registration a minted session names is read from.
PLATFORM_TABLE = "lti_platform"

# E1-08's own subject claim, named here because one method reads it back off a
# launched session to re-mint the same person's session as a control.
SUBJECT_CLAIM = "sub"

ROUTE_IS_OWED = (
    f"E4-18 ships `GET {SECTIONS_PATH}` in `app.api.instructor`, behind the same "
    "`require_instructor` dependency the module's two existing routes carry. Its 200 body is a "
    f"`{SECTIONS_MEMBER}` list whose entries carry `{SECTION_ID_FIELD}`, `{CODE_FIELD}` and "
    f"`{COURSE_LABEL_MEMBER}`, one for each section the session's person holds the "
    "teaching-instructor grant over — empty where that person teaches nothing. It has no 404: "
    "there is no parameter in this request to refuse."
)

# ---------------------------------------------------------------------------
# Her second section, and the second course it hangs off.
# ---------------------------------------------------------------------------

# The cohort her second section belongs to. **Its code has to sort *after* the
# taught section's**, because the order test's whole subject is that the declared
# order is neither the creation order nor the code order: `F1WW` is seeded first
# and `H1WW` second, so a list ordered by code alone answers them in creation
# order and is indistinguishable from no ordering at all. `H` is one of SPEC
# §2.2's own six-week start letters and is in `SEEDED_COHORTS`, so its length and
# start date are the seed's rather than this file's.
HER_SECOND_COHORT = "H"

# The number of the course her second section sits under. **Three characters
# beginning with a zero, deliberately.** `tests/fixtures/supervision.py` invents a
# course number in 100-799 for every course the seeding walker builds, and
# `lms_number` is a string column, so `099` sorts before every number that walker
# can produce — which puts her second section's *label* first while its *code*
# comes second. Without that disagreement the two orders coincide and the order
# criterion is asserted by nothing (`docs/MISTAKES.md` entry 3).
HER_SECOND_COURSE_NUMBER = "099"

# The title that course carries. Distinctive enough that finding it in a refusal
# body is unmistakable, and it is the only value of this course a test ever
# searches for on its own — the number is three digits and occurs inside uuids
# constantly (`tests/fixtures/student_read.py` says the same of its own).
HER_SECOND_COURSE_TITLE = "E4-18 second course: the one her section list has to carry as well"

# The subjects the two minted sessions name. Neither is a subject any launch in
# this suite signs, so a session carrying one cannot be confused with a session a
# door issued.
A_PERSON_WITHOUT_A_GRANT = "e4-18-instructor-holding-no-teaching-grant"
A_SESSION_WITHOUT_A_PERSON = "e4-18-session-naming-no-person"


class TaughtSection(NamedTuple):
    """One section, in the three currencies E4-18's entry carries it in.

    `code` and the row behind it come out of the database rather than out of this
    file, so what a test looks for is what is stored (`docs/MISTAKES.md` entry 30);
    `course_label` is composed by FIX-01 item 2's own reader over the same rows.
    """

    section_id: Any
    code: str
    course_label: str
    row: Any

    def spellings(self) -> set[str]:
        """Every string a JSON body could name this section by.

        A uuid hyphenated and hyphen-stripped — `str(...)` is what anything
        rendering one produces by default and `uuid.hex` is the near miss that
        walks through a search for the first — plus the code and the label, which
        are the other two ways this section has a name at all.
        """
        written = str(self.section_id)
        found = {written, written.replace("-", ""), self.code, self.course_label}
        return {value for value in found if value}


def surface_of(answered: Any) -> str:
    """Everything a client reading this response could see: its headers and its body.

    The headers as well as the body, because an identifier can ride one — a
    `Location`, an `ETag` built out of the row it describes — and a scan blind to
    them reports a clean answer. The same reader
    `tests/integration/test_the_report_route_names_nothing_about_a_section_she_does_not_teach.py`
    uses, kept here because two modules of this ticket need it.
    """
    headers = " ".join(f"{name}: {value}" for name, value in answered.headers.items())
    return f"{headers} {answered.text}"


def entries_in(answered: Any) -> list[Any]:
    """The `sections` list one answer carries, or a failure naming what came back instead.

    Called from a test body and never from a fixture, so a tree where the route is
    unbuilt produces a FAILED naming the deliverable rather than an error in
    somebody's setup (`docs/MISTAKES.md` entry 44). The status is checked here
    rather than in every caller, because a list read off a refusal is a list every
    later assertion is vacuously true of (`docs/MISTAKES.md` entry 3).
    """
    if answered.status_code != 200:
        pytest.fail(
            f"`GET {SECTIONS_PATH}` answered {answered.status_code} rather than 200 for a session "
            f"this route is meant to answer. Body begins {answered.text[:400]!r}.\n\n"
            f"{ROUTE_IS_OWED}"
        )
    body = decoded(answered, f"`GET {SECTIONS_PATH}`")
    if not isinstance(body, dict) or SECTIONS_MEMBER not in body:
        available = sorted(body) if isinstance(body, dict) else repr(body)
        pytest.fail(
            f"`GET {SECTIONS_PATH}` answered 200 carrying {available} and no `{SECTIONS_MEMBER}` "
            f"member.\n\n{ROUTE_IS_OWED}"
        )
    entries = body[SECTIONS_MEMBER]
    if not isinstance(entries, list):
        pytest.fail(
            f"`{SECTIONS_MEMBER}` came back as {type(entries).__name__} ({entries!r}); the "
            "ticket's public interface makes it a list, empty where the person teaches nothing."
        )
    return entries


def section_ids_in(entries: list[Any]) -> list[str]:
    """The `section_id` of each entry, in the order the answer put them in.

    A failure rather than a `KeyError` for an entry carrying no such member: the
    order and the shape are different criteria, and a traceback out of a subscript
    names neither.
    """
    found: list[str] = []
    for place, entry in enumerate(entries):
        if not isinstance(entry, dict) or SECTION_ID_FIELD not in entry:
            pytest.fail(
                f"Entry {place} of `{SECTIONS_MEMBER}` is {entry!r}, which carries no "
                f"`{SECTION_ID_FIELD}`. Every entry names its section: that is the whole reason "
                "this route exists, since every report route takes a section id and nothing the "
                "client holds supplies one."
            )
        found.append(str(entry[SECTION_ID_FIELD]))
    return found


class InstructorSections:
    """One instructor at the door with two sections, another with a third, and reads of the list.

    The door, the launch and the session are `tests/fixtures/report_api.py`'s; what
    this adds is the second grant, the third section's grant, and the four ways
    E4-18's route is asked — as her, as a minted session of two kinds, and with no
    credential at all.
    """

    def __init__(
        self,
        door: ReportDoor,
        *,
        hers: tuple[TaughtSection, TaughtSection],
        another_instructors: TaughtSection,
        her_person_id: Any,
        another_person_id: Any,
        web_identity: Any,
        configured: Mapping[str, str],
        platform_id: Any,
        issuer: str,
    ) -> None:
        self.door = door
        self.hers = hers
        self.another_instructors = another_instructors
        self.her_person_id = her_person_id
        self.another_person_id = another_person_id
        self.web_identity = web_identity
        self.configured = configured
        self.platform_id = platform_id
        self.issuer = issuer

    # -- asking the route -----------------------------------------------------

    def taught_sections(self, *, token: str | None = None) -> Any:
        """One read of E4-18's route, carrying exactly one credential.

        The jar is emptied for every call, hers included, so each request carries
        the session the caller named and nothing else: E1-08 delivers a session as
        a `Set-Cookie` on the landing redirect as well as in the URL fragment, and
        `httpx` sends jar cookies on every later request to the same host — so a
        read made with a minted token through the client her launch was driven
        with would otherwise carry her session too (`docs/disputes/E2-09-01.md`).
        """
        with self.door.carrying_no_cookie():
            return self.door.tool.get(
                SECTIONS_PATH,
                headers={
                    "authorization": (
                        f"{AUTHENTICATE_SCHEME} {self.door.token if token is None else token}"
                    )
                },
            )

    def without_a_session(self) -> Any:
        """The same read carrying no credential of any kind — no header, and no cookie."""
        with self.door.carrying_no_cookie():
            return self.door.tool.get(SECTIONS_PATH)

    # -- the two sessions criterion 3 is about --------------------------------

    def a_session_naming_a_person_with_no_teaching_grant(self) -> str:
        """An instructor session for a person who holds no assignment at all.

        Seeded and minted rather than launched, and the ticket is why: E1-13
        resolves a landing from the assignment model, so a person with no
        assignment lands on the calm no-access page and there is no launch that
        issues this session. The person is named **both** ways a request could
        resolve one — the `person_id` claim E1-12 adds, and a `user` row this
        person is linked to — so the case does not rest on which of the two the
        implementer reads.
        """
        person_id = self.web_identity.person()
        user_id = self.web_identity.user(
            platform_id=self.platform_id, subject=A_PERSON_WITHOUT_A_GRANT
        )
        self.web_identity.link_person_to_user(person_id=person_id, user_id=user_id)
        return self._minted(subject=A_PERSON_WITHOUT_A_GRANT, user_id=user_id, person_id=person_id)

    def a_session_naming_no_person(self) -> str:
        """An instructor session carrying no person at all, either way one could be named.

        A `user` row with no `person` pointing at it, and a null `person_id` claim.
        ADR 0028 makes "no person" a defined session-carried state rather than an
        error, and E4-18 makes it an empty list rather than a refusal: there is no
        parameter in this request to refuse.
        """
        user_id = self.web_identity.user(
            platform_id=self.platform_id, subject=A_SESSION_WITHOUT_A_PERSON
        )
        return self._minted(subject=A_SESSION_WITHOUT_A_PERSON, user_id=user_id, person_id=None)

    def a_session_minted_for_her(self) -> str:
        """Her own session, re-minted through the helper the two cases above use.

        **The control on the minting itself** (`docs/MISTAKES.md` entry 35). The
        two sessions above are the only way to reach criterion 3's cases, and each
        of them expects a 200 — so a minted token this application refuses for
        some reason of its own would turn both into refusals and read exactly like
        a route that declines to answer them. This one carries the same three
        claims her launched session carries — the subject, the launch-side `user`
        row and the person — so a 200 here and a 200 there are the same statement
        about the same machinery, and a red here says the machinery rather than
        the route.
        """
        claims = claims_in_session(self.door.token)
        subject = claims.get(SUBJECT_CLAIM)
        user_id = claims.get(USER_ID_CLAIM)
        assert isinstance(subject, str) and subject, (
            f"Her launched session carries no `{SUBJECT_CLAIM}` — it carries {sorted(claims)}, and "
            "E1-08 puts the verified subject there on every session either door issues."
        )
        return self._minted(subject=subject, user_id=user_id, person_id=self.her_person_id)

    def _minted(self, *, subject: str, user_id: Any, person_id: Any) -> str:
        """One `INSTRUCTOR` session, minted through the module both doors issue through.

        **Bound by signature rather than by a spelling this file chose.** E1-08's
        interface ruling names `issue_session` and settles no signature, and E1-12
        adds `person_id` to `SessionClaims` without settling how it is passed — so
        a parameter naming a person is filled by name and a module that has none
        is a failure saying so, which is an interface question rather than a guess
        (the device `tests/fixtures/submit.py::issue_student_session` uses, whose
        invocation this copies rather than rewrites — `docs/MISTAKES.md` entry 37).

        The values are `str(...)` and not the raw keys: `person.id` and `user.id`
        are `uuid.UUID` out of the database (ADR 0016) and a session is a JWT, so a
        uuid handed straight through dies in `json.dumps` inside this helper.
        """
        import inspect

        import app.services.session as session_module
        from app.services.authz import Door, LandingRole

        issue = getattr(session_module, "issue_session", None)
        if not callable(issue):
            pytest.fail(
                "`app.services.session` exposes no `issue_session`. E1-08 puts the shared session "
                "module there and both doors issue through it; E4-18's two empty-list cases are "
                "sessions no launch can produce, so there is no other way to stand at the door as "
                "one."
            )
        role = getattr(LandingRole, INSTRUCTOR_ROLE, None)
        if role is None:
            pytest.fail(
                f"`LandingRole` has no member {INSTRUCTOR_ROLE!r}; it has "
                f"{sorted(member.name for member in LandingRole)}."
            )
        parameters = inspect.signature(issue).parameters
        naming_a_person = [name for name in parameters if "person" in name.lower()]
        if len(naming_a_person) != 1 or "user_id" not in parameters:
            pytest.fail(
                f"`issue_session{inspect.signature(issue)}` declares {naming_a_person} naming a "
                "person and "
                f"{'a' if 'user_id' in parameters else 'no'} `user_id`. E1-12 adds both to "
                "`SessionClaims` — `person_id` is the stored identity and `user_id` the "
                "launch-side row — and E4-18's criterion 3 turns on the difference between a "
                "session that names a person and one that does not, so this suite has to be able "
                "to mint each."
            )
        values: dict[str, Any] = {
            "door": Door.LAUNCH,
            "role": role,
            "sub": subject,
            "iss": self.issuer,
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
                "fill and it has no value for them. A further required input is an interface "
                "question for the ticket — `_minted` in tests/fixtures/instructor_sections.py is "
                "where a spelling is taught."
            )
        return issue(**values)


# ---------------------------------------------------------------------------
# Building the world.
# ---------------------------------------------------------------------------


def _the_person_the_session_names(door: ReportDoor) -> Any:
    """The `person` this launch resolved to, off the session it issued.

    Read out of the session rather than kept by `report_api.py`'s door, which
    discards it: E1-12 puts `person_id` in the claims precisely so that what a
    request resolves is stated, and reading it here means the second grant is
    written for the person the door will actually be answered as. A launch that
    resolved to nobody would otherwise leave this file writing a grant for a person
    no request ever names, and every scope assertion in the ticket would be about
    an empty list.
    """
    claims = claims_in_session(door.token)
    value = claims.get(PERSON_ID_CLAIM)
    assert isinstance(value, str) and value, (
        f"The instructor session this launch issued carries no `{PERSON_ID_CLAIM}` — it carries "
        f"{sorted(claims)}. E1-12 makes that claim the stored identity a launch resolves to, and "
        "this world writes her second teaching grant for it."
    )
    try:
        return UUID(value)
    except ValueError:
        pytest.fail(
            f"The session's `{PERSON_ID_CLAIM}` is {value!r}, which is not a uuid. ADR 0016 makes "
            "every key one, and a `role_assignment` row cannot be written for anything else."
        )


def _a_section_of_a_second_course(world: Any) -> Any:
    """Her second section, under a second course of the same prefix. See `HER_SECOND_COHORT`.

    The chain is the world's own with the course and section levels dropped, which
    is how `tests/fixtures/student_read.py::seed_a_course_this_student_is_not_in`
    puts a section under a course of its choosing: the seeding walker fills any
    ancestor a chain does not carry and reuses every one it does, so the term and
    the prefix above this course are the world's and the course itself is new.

    The section's own calendar is `SEEDED_COHORTS`' — transcribed from
    `scripts/seed.py` — and its end date is ADR 0020's inclusive convention, the
    same two lines `Fall2026.section_row` writes. Nothing derived here is anything
    a test reads back as an answer.
    """
    chain = dict(world.calendar.chain)
    for level in (SECTION_TABLE, COURSE_TABLE):
        chain.pop(level, None)
    assert PREFIX_TABLE in chain and TERM_TABLE in chain, (
        f"The world's containment chain holds {sorted(chain)}, and this needs the `{PREFIX_TABLE}` "
        f"and `{TERM_TABLE}` rows above it to hang a second course off the same prefix. Without "
        "the prefix the walker builds a fresh one, whose invented code decides the label order "
        "this file is choosing on purpose."
    )
    world.seed(
        COURSE_TABLE,
        chain,
        **{
            COURSE_NUMBER_COLUMN: HER_SECOND_COURSE_NUMBER,
            COURSE_TITLE_COLUMN: HER_SECOND_COURSE_TITLE,
        },
    )
    length_weeks, _first_term_week, start = SEEDED_COHORTS[HER_SECOND_COHORT]
    return world.seed(
        SECTION_TABLE,
        chain,
        **{
            SECTION_CODE_COLUMN: (
                f"{HER_SECOND_COHORT}{COHORT_SECTION_ORDINAL}{COHORT_SECTION_MODALITY}"
            ),
            SECTION_LENGTH_COLUMN: length_weeks,
            SECTION_START_COLUMN: start,
            SECTION_END_COLUMN: start + timedelta(days=length_weeks * 7 - 1),
        },
    )


def _facts_about(row: Any, labels: StudentReadWorld, key: str) -> TaughtSection:
    """One seeded section as the three values an entry carries, read off the rows."""
    return TaughtSection(
        section_id=row[key],
        code=row[SECTION_CODE_COLUMN],
        course_label=labels.course_label_of(row),
        row=row,
    )


def build_instructor_sections(
    door: ReportDoor,
    committed_rows: Any,
    metadata_tables: dict[str, Any],
    web_identity: Any,
    configured: Mapping[str, str],
) -> InstructorSections:
    """Seed the second section, write the two grants, and answer the world's keys.

    In this order, and every step of it is somebody's existing machinery: the
    launch, the session and the first grant are `report_api.py`'s, the rows are
    committed because the tool connects for itself (ADR 0001), and the label is
    composed by FIX-01 item 2's own reader.

    **The premise checks at the foot are the fixture's, deliberately.** They are
    claims about the rows this file wrote — three distinct sections, two grants for
    her, one for the other instructor — and not about anything E4-18 owes, so a
    failure here is a defect in this world rather than a red about the route
    (`docs/MISTAKES.md` entry 13's closing sentence). Without them a grant that
    silently failed to land would leave the absence assertion in the scope module
    passing because *nobody* teaches the third section, which is a different fact
    from the one it claims to prove (`docs/MISTAKES.md` entry 30).
    """
    world = door.rows.world
    labels = StudentReadWorld(committed_rows, metadata_tables)
    key = world.key_of(SECTION_TABLE)

    her_first = world.section(TAUGHT_COHORT)
    another_instructors = world.section(UNTAUGHT_COHORT)
    her_second = _a_section_of_a_second_course(world)
    committed_rows.commit()

    her_person_id = _the_person_the_session_names(door)
    another_person_id = web_identity.person()
    committed_rows.graph.assign(INSTRUCTOR_ROLE, scope=her_second[key], person=her_person_id)
    committed_rows.graph.assign(
        INSTRUCTOR_ROLE, scope=another_instructors[key], person=another_person_id
    )
    committed_rows.commit()

    sections = (her_first, her_second, another_instructors)
    assert len({row[key] for row in sections}) == len(sections), (
        "The three sections this world is built on are not three rows: "
        f"{[row[SECTION_CODE_COLUMN] for row in sections]} carry {[row[key] for row in sections]}."
    )
    hers = committed_rows.graph.assignments_of(her_person_id)
    theirs = committed_rows.graph.assignments_of(another_person_id)
    assert len(hers) == 2 and len(theirs) == 1, (
        f"The launching instructor holds {len(hers)} assignments and the other instructor "
        f"{len(theirs)}; this world is two and one. Her first is the `INSTRUCTOR` row scoped to "
        f"the taught section that `tests/fixtures/report_api.py` writes at launch, her second is "
        "written here, and the other instructor's is the grant that makes the third section "
        "somebody's rather than nobody's — an absence assertion over a section no one teaches "
        "would pass against a read that filters on the role and forgets the person."
    )

    registration = door.driver.registration
    platform_id = registration.platform_row[
        single_primary_key(require_table(metadata_tables, PLATFORM_TABLE))
    ]
    return InstructorSections(
        door,
        hers=(
            _facts_about(her_first, labels, key),
            _facts_about(her_second, labels, key),
        ),
        another_instructors=_facts_about(another_instructors, labels, key),
        her_person_id=her_person_id,
        another_person_id=another_person_id,
        web_identity=web_identity,
        configured=configured,
        platform_id=platform_id,
        issuer=registration.platform_row[registration.issuer_column],
    )


@pytest.fixture
def instructor_sections(
    report_door: ReportDoor,
    committed_rows: Any,
    metadata_tables: dict[str, Any],
    web_identity: Any,
    configured_env: dict[str, str],
) -> InstructorSections:
    """The teaching instructor with two sections, and somebody else with a third.

    `configured_env` is asked for here rather than in each module because the two
    minted sessions are signed with the secret it lays down, and because the door
    underneath already rides it — asking for it twice is the same mapping, not a
    second environment (`docs/MISTAKES.md` entry 40).
    """
    return build_instructor_sections(
        report_door, committed_rows, metadata_tables, web_identity, configured_env
    )
