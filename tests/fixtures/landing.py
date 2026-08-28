"""What a session may act as, and the rows that decide it — E1-13.

E1-13 deletes `backend/app/services/landing.py` and resolves the landing view from
the **assignment model** instead of from a verified token's roles claim: the
person's live assignments, filtered by the entered door's permission column (ADR
0026's `permits_launch` / `permits_web_login`), with enrollment as the student
fallback at the launch door alone (ADR 0028, SPEC §2.1). Three things live here,
and each is here rather than in a test module because more than one module needs
it (`docs/MISTAKES.md` entry 13).

**`landing_contract` is the settled vocabulary, transcribed once.** The work order
settles every name before any code is written — `Door`, `LandingRole`,
`LANDING_FOR_ROLE`, `LANDING_PRECEDENCE`, `chosen_landing`, `resolve_landing` in
`app.services.authz`; `no_access()` and its `no-access` testid in `app.api.deps` —
so this is a transcription of a contract rather than a guess at one, and a name
that turns out to be wrong is one line here rather than a rewrite. The module
itself is reached through the `authz` fixture (`tests/fixtures/authz_data.py`),
which turns an absent module or an absent symbol into a failed assertion instead
of a collection error: an import error is not a red.

**`enrol` writes one `enrollment` row with the window the caller chose**,
committed. The window is never this fixture's choice — criterion 5 is entirely
about which side of the boundary a date falls on, so a fixture that picked the
dates would be supplying the value under test (`docs/MISTAKES.md` entry 30).
What it does own is the *column discovery*: `enrollment`'s two links are followed
through their foreign keys rather than guessed at by name, because a
`row.get("user_id")` that answers `None` for every row seeds an enrollment
belonging to nobody and leaves a student landing nowhere for a reason no
assertion is about.

**`landing_ground` gives a launching subject something to land on**, for the
suites whose subject is *not* which view a person reaches but which do need a
landing to exist. From E1-13 on, a launch by a subject with no assignment and no
live enrollment lands on the calm no-access page rather than on a role route, so
tests about signatures, nonces, cookies and §4.1 scans over a landing stop having
one (`docs/MISTAKES.md` entry 22). Two modules take that repair —
`tests/integration/test_lti_launch_door.py` and
`tests/integration/test_the_launch_views_name_nobody.py` — through their own
fixtures built on this.

**The provisioning suites deliberately do not, and it is worth knowing why before
anybody offers them this.** `test_launch_time_provisioning.py`,
`test_launch_provisioning_defects.py`,
`test_provisioning_consults_the_catalog_at_every_write.py`,
`test_provisioning_reads_its_environment_and_its_day_from_settings.py` and
`test_the_leadership_limb_of_a_staff_launch.py` assert over the *rows* a launch
writes — several of them that `course`, `section` or `user` is entirely empty, or
that exactly one section exists — and every route to a landing writes into at
least one of those tables. Worse, the section this seeds takes its code from the
suite-wide `{letter}3WW` generator, which produces `R3WW` — the mock's own launch
code — within 26 draws. Those modules assert `LaunchDriver.accepted` instead: the
door did not refuse, which is exactly E1-10's own rule, and each says so in its
docstring.

**It is deliberately not used by `tests/integration/test_landing_resolves_from_
assignments.py`.** That module's whole subject is which view a set of rows
produces, so it writes its rows in the open where the assertion can see them.
A fixture that chose the assignment for it would be handing back its own answer.

**The environment** (`docs/MISTAKES.md` entry 40): everything here rides
`committed_rows`, which rides `migrated_engine` and therefore `migrated_database`
— the testcontainers Postgres, migrated in process with the whole process
environment snapshotted and restored around the upgrade. Nothing here reads
`os.environ` and nothing here sets it; the doors these rows are read through
state their own environment through `tool_doors`. Teardown is `committed_rows`'s
diff-delete, so a row written here — or written by the application on its own
connection while a test runs — is removed when the test ends.
"""

from collections.abc import Callable
from datetime import date
from typing import Any, NamedTuple

import pytest

from fixtures.supervision import foreign_key_columns, require_table

# ---------------------------------------------------------------------------
# The names E1-13 settles, transcribed once.
# ---------------------------------------------------------------------------

# Where the resolution lives. The ticket header says why — "what a session may act
# as is authorization's first question" — and the work order (D1) records that it
# is also forced: `public.assignment_scope` may be read from `authz.py` and from
# nowhere else (`tests/unit/test_the_org_views_are_read_only_through_the_grant.py`).
AUTHZ_MODULE = "app.services.authz"

# The six public names E1-13 adds to (or moves into) that module. `Door` and
# `LandingRole` move from the deleted `app/services/landing.py` with their member
# names unchanged — `verified_session` reads `Door[...]`/`LandingRole[...]` by
# member name, so a rename in the move breaks every session round-trip.
DOOR_ENUM = "Door"
LANDING_ROLE_ENUM = "LandingRole"
LANDING_FOR_ROLE = "LANDING_FOR_ROLE"
LANDING_PRECEDENCE = "LANDING_PRECEDENCE"
CHOSEN_LANDING = "chosen_landing"
RESOLVE_LANDING = "resolve_landing"

# Where the door pages live from E1-13 on (D5): `PAGE`, `refusal_page`,
# `cancelled_page`, `no_account_page` and the new `no_access` move into the module
# whose docstring already describes them. No new module.
DEPS_MODULE = "app.api.deps"
NO_ACCESS_FUNCTION = "no_access"

# The four pages a door can answer with that are not a landing, by the testid each
# is addressed by. Four distinguishable answers, because "nothing here gives you a
# view", "Pulse has no record of you", "you cancelled" and "this tool refuses your
# token" are four events and the person in front of the screen is owed different
# words for each.
NO_ACCESS_TESTID = "no-access"
NO_ACCOUNT_TESTID = "no-account"
CANCELLED_TESTID = "web-login-cancelled"
REFUSED_TESTID = "pulse-entry-refused"

# E1-04's route group names, which E1-08's `fragment_redirect` builds `/app/<role>`
# from. Five, one per `LandingRole` member.
STUDENT_ROUTE = "student"
INSTRUCTOR_ROUTE = "instructor"
LEADERSHIP_ROUTE = "leadership"
CARE_ROUTE = "care"
ADMIN_ROUTE = "admin"

# Where the LIS vocabulary lives from E1-13 on (D7): `LTI_ROLES_CLAIM`,
# `MEMBERSHIP_VOCABULARY`, `INSTRUCTOR_ROLE_URI`, `LEARNER_ROLE_URI` and
# `stated_roles` move to the module SPEC §13 describes as "launch validation,
# role/context resolution". Named here so the one test that asserts the move has a
# single spelling to fail on.
LAUNCH_MODULE = "app.lti.launch"
LAUNCH_VOCABULARY_NAMES = (
    "LTI_ROLES_CLAIM",
    "MEMBERSHIP_VOCABULARY",
    "INSTRUCTOR_ROLE_URI",
    "LEARNER_ROLE_URI",
    "stated_roles",
)

# The module E1-13 deletes outright, and the seam inside it both routers used to
# call. Named so that "it is gone" is a statement about a spelling rather than
# about a feeling.
RETIRED_MODULE = "app.services.landing"
RETIRED_SEAM = "landing_role_for"

# ADR 0026's two generated columns, which `assignment_scope` withholds until this
# ticket's `_v002` (D4). A door only admits the assignments that permit it, and
# these are where that fact is readable from SQL.
PERMITS_LAUNCH_COLUMN = "permits_launch"
PERMITS_WEB_LOGIN_COLUMN = "permits_web_login"
ASSIGNMENT_SCOPE_VIEW = "assignment_scope"

# E0-08's two date columns on `enrollment` — Pulse's own record of when a member
# was first and last seen — spelled as `tests/fixtures/roster_sync.py` spells them.
# ADR 0020's convention makes the end date the last *included* day, which is the
# whole of what criterion 5's boundary turns on.
STARTED_ON_COLUMN = "started_on"
ENDED_ON_COLUMN = "ended_on"
ENROLLMENT_TABLE = "enrollment"

# The one role this module writes an assignment for. Spelled as SPEC §2.1's
# canonical chain spells it, which is also how
# `tests/fixtures/supervision.py::ROLE_ALIASES` keys it. Every other role belongs
# to the test that means it: a fixture with a menu of roles is a fixture choosing
# which view a person gets.
INSTRUCTOR_ROLE = "INSTRUCTOR"


class LandingContract(NamedTuple):
    """Every name E1-13 settles, handed to a test module rather than transcribed.

    Reached as a fixture rather than imported, for the reason every other fixtures
    module in this suite gives: an import of a fixtures module by name depends on
    where pytest put `tests/` on `sys.path`, and an import error is not a red.
    """

    authz_module: str
    deps_module: str
    launch_module: str
    retired_module: str
    retired_seam: str
    door_enum: str
    landing_role_enum: str
    landing_for_role: str
    landing_precedence: str
    chosen_landing: str
    resolve_landing: str
    no_access_function: str
    no_access_testid: str
    no_account_testid: str
    cancelled_testid: str
    refused_testid: str
    launch_vocabulary_names: tuple[str, ...]
    permits_launch_column: str
    permits_web_login_column: str
    assignment_scope_view: str
    routes: dict[str, str]


@pytest.fixture
def landing_contract() -> LandingContract:
    """The names E1-13 settles. See `LandingContract` and this module's docstring."""
    return LandingContract(
        authz_module=AUTHZ_MODULE,
        deps_module=DEPS_MODULE,
        launch_module=LAUNCH_MODULE,
        retired_module=RETIRED_MODULE,
        retired_seam=RETIRED_SEAM,
        door_enum=DOOR_ENUM,
        landing_role_enum=LANDING_ROLE_ENUM,
        landing_for_role=LANDING_FOR_ROLE,
        landing_precedence=LANDING_PRECEDENCE,
        chosen_landing=CHOSEN_LANDING,
        resolve_landing=RESOLVE_LANDING,
        no_access_function=NO_ACCESS_FUNCTION,
        no_access_testid=NO_ACCESS_TESTID,
        no_account_testid=NO_ACCOUNT_TESTID,
        cancelled_testid=CANCELLED_TESTID,
        refused_testid=REFUSED_TESTID,
        launch_vocabulary_names=LAUNCH_VOCABULARY_NAMES,
        permits_launch_column=PERMITS_LAUNCH_COLUMN,
        permits_web_login_column=PERMITS_WEB_LOGIN_COLUMN,
        assignment_scope_view=ASSIGNMENT_SCOPE_VIEW,
        routes={
            "student": STUDENT_ROUTE,
            "instructor": INSTRUCTOR_ROUTE,
            "leadership": LEADERSHIP_ROUTE,
            "care": CARE_ROUTE,
            "admin": ADMIN_ROUTE,
        },
    )


# ---------------------------------------------------------------------------
# One `enrollment` row, with the window the caller chose.
# ---------------------------------------------------------------------------


class EnrollmentRows:
    """`enrollment` rows written committed, with their two links followed rather than named.

    Committed because every door in this suite is driven over HTTP against an
    application that opens its own connection out of `DATABASE_URL` and sees
    nothing that has not been.

    **The window is always the caller's.** ADR 0028 makes enrollment the whole of
    a student's access and ADR 0020 makes an end date the last included day, so
    which day a window covers is the fact criterion 5 is about — and a default here
    would decide it.
    """

    def __init__(self, rows: Any, tables: dict[str, Any]) -> None:
        self.rows = rows
        self.tables = tables

    def link(self, target: str) -> str:
        """The column on `enrollment` whose foreign key points at `target`.

        Followed rather than spelled. `enrollment.user_id` is almost certainly
        called that, and "almost certainly" is how a fixture ends up writing
        `None` into every row: an enrollment belonging to no user satisfies the
        insert and leaves a student landing nowhere, which reads exactly like the
        resolution being wrong.
        """
        table = require_table(self.tables, ENROLLMENT_TABLE)
        found = foreign_key_columns(table, target)
        if len(found) != 1:
            pytest.fail(
                f"`{ENROLLMENT_TABLE}` has {len(found)} foreign keys to `{target}` ({found}); it "
                f"references "
                f"{sorted({key.column.table.name for key in table.foreign_keys})}. SPEC §8 gives "
                "an enrollment one user and one section, and every row seeded here is addressed "
                "through those two."
            )
        return found[0]

    def enrol(
        self,
        *,
        user_id: Any,
        section_id: Any,
        started_on: date,
        ended_on: date | None,
    ) -> Any:
        """One `enrollment` row for this user in this section, over this window.

        `ended_on=None` is the open window a roster sync leaves on a member it is
        still seeing; a date is the last day the member was enrolled (ADR 0020's
        `'[]'` convention, and ADR 0023's check constraint requires it not to
        precede `started_on`).
        """
        table = require_table(self.tables, ENROLLMENT_TABLE)
        for column in (STARTED_ON_COLUMN, ENDED_ON_COLUMN):
            if column not in table.c:
                pytest.fail(
                    f"`{ENROLLMENT_TABLE}` declares no `{column}` (it declares "
                    f"{[c.name for c in table.columns]}). E0-08 created both, and the boundary "
                    "E1-13's criterion 5 is about is a comparison between them and the "
                    "institution's current day."
                )
        row = self.rows.seed(
            ENROLLMENT_TABLE,
            {},
            **{
                self.link("user"): user_id,
                self.link("section"): section_id,
                STARTED_ON_COLUMN: started_on,
                ENDED_ON_COLUMN: ended_on,
            },
        )
        self.rows.commit()
        return row


@pytest.fixture
def enrol(committed_rows: Any, metadata_tables: dict[str, Any]) -> EnrollmentRows:
    """`enrollment` rows with the window the caller chose. See `EnrollmentRows` above."""
    return EnrollmentRows(committed_rows, metadata_tables)


# ---------------------------------------------------------------------------
# Something for a launching subject to land on, for the suites that are about
# something else.
# ---------------------------------------------------------------------------


class LandingGround:
    """The rows that let a launch by `subject` reach a role route at all.

    From E1-13 on a landing is resolved from the assignment model, so a launch by
    a subject Pulse holds no record of lands on the calm no-access page. That is
    the ticket's rule and it is correct; it also breaks every launch-driving test
    in this suite whose subject is a signature, a nonce or a §4.1 scan over what a
    landing carries (`docs/MISTAKES.md` entry 22). Both methods below are that
    repair — the minimum row set that makes such a launch land, written once.

    **Neither method is used by the module whose subject is the landing.** There,
    the rows are the question and they are written in the open.

    **Neither is used by the provisioning suites either**, for the two reasons the
    module docstring gives: they assert over the very tables a landing has to be
    built out of, and the section code this seeds can collide with the mock's own.
    """

    def __init__(self, rows: Any, identity: Any, enrolments: EnrollmentRows) -> None:
        self.rows = rows
        self.identity = identity
        self.enrolments = enrolments

    def a_student(self, *, platform_id: Any, subject: str, on: date) -> dict[str, Any]:
        """A `user` row for `subject` and a live enrollment containing `on`.

        No `person` row and no assignment: ADR 0028 gives a student neither, and a
        student's access resolves from enrollment alone. `on` is the caller's day —
        the institution's, per D3 — so this fixture never decides which day a
        window has to contain.
        """
        user_id = self.identity.user(platform_id=platform_id, subject=subject)
        section_id = self.rows.graph.scope("section")
        self.rows.commit()
        enrollment = self.enrolments.enrol(
            user_id=user_id, section_id=section_id, started_on=on, ended_on=None
        )
        return {"user_id": user_id, "section_id": section_id, "enrollment": enrollment}

    def an_instructor(self, *, platform_id: Any, subject: str) -> dict[str, Any]:
        """A `person`, a `user` row for `subject`, ADR 0024's link, and one `INSTRUCTOR` row.

        The four rows a launching instructor is made of: the launch resolves `sub`
        → `user` → `person` (E1-12) and the assignment is what the door then reads
        (§2.1, E0-09).
        """
        person_id = self.identity.person()
        user_id = self.identity.user(platform_id=platform_id, subject=subject)
        self.identity.link_person_to_user(person_id=person_id, user_id=user_id)
        assignment = self.rows.graph.assign(
            INSTRUCTOR_ROLE, scope=self.rows.graph.fresh_scope("section"), person=person_id
        )
        self.rows.commit()
        return {"person_id": person_id, "user_id": user_id, "assignment": assignment}


@pytest.fixture
def landing_ground(
    committed_rows: Any, web_identity: Any, enrol: EnrollmentRows
) -> Callable[[], LandingGround]:
    """Something for a launching subject to land on. See `LandingGround` above.

    A factory rather than an instance so that a test which builds it can say, in
    its own body, which subject it is standing up — reading a fixture's name in a
    parameter list is not the same as seeing the rows a launch depends on.
    """

    def build() -> LandingGround:
        return LandingGround(committed_rows, web_identity, enrol)

    return build
