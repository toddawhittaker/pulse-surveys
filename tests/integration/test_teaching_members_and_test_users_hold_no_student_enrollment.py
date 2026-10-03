"""Enrollment means "student" — E5.1-02, criterion 4.

"A roster member carrying Instructor, or `…/lti/system/person#TestUser`, holds no
open enrollment after a walk, and an existing open one is closed. Such a person's
launch does not land as STUDENT for that section, and `POST /student/submissions`
refuses them."

Before this ticket the sync wrote an enrollment for every roster member, and a
launch with no assignment but a live enrollment lands as STUDENT. So staff and
the LMS's own preview accounts were counted as respondents, could open the
student survey, and could submit into it.

**Three layers, each asserted where it is observable.**

  - **The rows.** A walk leaves a teaching member or a test user with no
    enrollment that covers today. "Open" is read the way the landing and the
    submit path read it — `ended_on IS NULL OR ended_on >= today` (work order
    D5) — so an enrollment closed *with* today, which still lets its holder in
    today, is not mistaken for a closed one.
  - **The landing.** A real LTI launch by such a person, after the walk, lands on
    E1-13's calm no-access page rather than on the student route.
  - **The submission.** A student session issued while the enrollment was open is
    refused by `POST /student/submissions` after the walk, with exactly the body a
    section that does not exist gets — and it was accepted before the walk, in the
    same world.

**Every pair is Learner against Instructor or TestUser**, in the same shape, so
the sync is never credited for refusing everybody: a plain Learner keeps an open
enrollment, still lands as a student, and can still submit.

**Every walk runs on `pulse_app`'s own connection** (`application_session`,
`docs/MISTAKES.md` entry 46): closing an enrollment spends the sync's column grant
on `enrollment.ended_on`, and a superuser-driven sync would pass whatever that
grant is.

**Which failure a red is, before E5.1-02 lands.** Every red here is an assertion
about a row, a landing or a status. The Learner halves are green today and are the
controls.

Marked `invariant` at the module level: a person the roster says is staff being
answered as a student — counted, shown the survey, allowed to write a response —
is a §4.1 visibility failure, and the module's refusals belong in the isolated
pass.
"""

from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlsplit
from uuid import uuid4

import pytest
from fixtures.landing import NO_ACCESS_TESTID
from fixtures.roster_sync import (
    INSTRUCTOR_ROLE_URN,
    LEARNER_ROLE_URN,
    TEST_USER_ROLE_URN,
    WalkableSection,
    institution_today,
    live_enrollments,
    roster_member,
    walk_a_synced_section,
)
from fixtures.student_read import STUDENT_LANDING, session_token_at
from fixtures.submit import SECTION_TABLE, SubmitWorld, a_valid_submission
from fixtures.supervision import require_table, single_primary_key

pytestmark = [pytest.mark.integration, pytest.mark.lti, pytest.mark.invariant]

# The role lists criterion 4 is about, and the one it is not. A teaching member
# is one whose roles carry the Instructor URI, whatever else they carry; a test
# user is one whose roles carry the TestUser URI, whatever else they carry —
# including Learner, which is how a platform's preview account usually arrives.
NOT_A_STUDENT = {
    "instructor": [INSTRUCTOR_ROLE_URN],
    "instructor-and-learner": [INSTRUCTOR_ROLE_URN, LEARNER_ROLE_URN],
    "test-user-and-learner": [LEARNER_ROLE_URN, TEST_USER_ROLE_URN],
    "test-user": [TEST_USER_ROLE_URN],
}
A_STUDENT = [LEARNER_ROLE_URN]

# How long before the walk an existing enrollment was opened. Weeks, so that
# closing it on any day up to and including yesterday is a legal row
# (`ended_on >= started_on`) and closing it with today is distinguishable.
WEEKS_AGO = 3


def weeks_ago(weeks: int) -> Any:
    return (datetime.now(UTC) - timedelta(days=weeks * 7)).date()


def platform_of(section: Any, metadata_tables: dict[str, Any]) -> Any:
    return section.registration.platform_row[
        single_primary_key(require_table(metadata_tables, "lti_platform"))
    ]


# ---------------------------------------------------------------------------
# The rows.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("kind", sorted(NOT_A_STUDENT))
def test_a_new_member_who_teaches_or_is_a_test_user_gets_no_open_enrollment(
    kind: str,
    roster_sync: Any,
    synced_section: Any,
    service_wire: Any,
    roster_rows: Any,
    application_session: Any,
    a_subject: Any,
) -> None:
    """Criterion 4, first half, for a member the sync meets for the first time.

    One walk serves the member under test and a plain learner beside them. The
    learner must get an open enrollment — that is the control that the walk
    ingested at all — and the member under test must hold none that covers today.

    **The mutations this kills:** an enrollment written for every member (today's
    tree); a check that reads only the *first* role, which the
    `test-user-and-learner` case defeats; a check that treats any Learner role as
    decisive, which `instructor-and-learner` defeats; and the TestUser URI matched
    as a substring of something else, which the `test-user` case pins as exact.
    """
    member = a_subject(f"not-a-student-{kind}")
    learner = a_subject("plain-learner")
    walk_a_synced_section(
        roster_sync,
        synced_section,
        service_wire,
        application_session,
        [
            roster_member(member, roles=NOT_A_STUDENT[kind]),
            roster_member(learner, roles=A_STUDENT),
        ],
    )
    today = institution_today()
    assert live_enrollments(roster_rows.enrollments_for(learner), today), (
        f"The plain learner {learner!r} holds no open enrollment after the walk, so the walk did "
        "not ingest this roster and the assertion below would hold for a sync that writes nothing."
    )
    held = live_enrollments(roster_rows.enrollments_for(member), today)
    assert not held, (
        f"A member whose roles are {NOT_A_STUDENT[kind]} holds an open enrollment after the walk: "
        f"{[dict(row) for row in held]}. Enrollment means 'student' (E5.1-02 criterion 4): a "
        "teaching member or a test user counted as one is a respondent who is not there."
    )


@pytest.mark.parametrize("kind", ["instructor", "test-user-and-learner"])
def test_an_existing_open_enrollment_of_a_member_who_is_not_a_student_is_closed_before_today(
    kind: str,
    roster_sync: Any,
    synced_section: Any,
    service_wire: Any,
    roster_rows: Any,
    seed_a_member: Any,
    application_session: Any,
    a_subject: Any,
) -> None:
    """Criterion 4: "an existing open one is closed" — and closed so that today is outside it.

    The member was enrolled three weeks ago, out of band, and a walk now lists
    them as a teacher or a test user. Their enrollment must stop covering today,
    and a second walk must not reopen it or open another. A learner seeded the
    same way and listed as a learner keeps hers open, in the same walks.

    **The mutations this kills:** leaving the existing row open (today's tree);
    closing it with today, which the live test `ended_on >= today` still reads as
    live — so the person lands as a student and submits today — and which a
    check on `ended_on IS NOT NULL` alone would pass; and a second walk that
    reopens it, which the re-add path would do if it did not know the member is
    staff.
    """
    member = a_subject(f"was-a-student-{kind}")
    learner = a_subject("still-a-student")
    seed_a_member(synced_section, member, started_on=weeks_ago(WEEKS_AGO))
    seed_a_member(synced_section, learner, started_on=weeks_ago(WEEKS_AGO))
    today = institution_today()
    assert live_enrollments(roster_rows.enrollments_for(member), today), (
        "The seeded enrollment does not cover today before the walk, so the assertion below would "
        "hold for a reason that has nothing to do with the walk."
    )

    roster = [
        roster_member(member, roles=NOT_A_STUDENT[kind]),
        roster_member(learner, roles=A_STUDENT),
    ]
    for walk in ("first", "second"):
        walk_a_synced_section(
            roster_sync, synced_section, service_wire, application_session, roster
        )
        assert live_enrollments(roster_rows.enrollments_for(learner), today), (
            f"After the {walk} walk the learner listed as a learner no longer holds an open "
            "enrollment, so the walk closed everybody and the assertion below proves nothing."
        )
        rows = roster_rows.enrollments_for(member)
        assert rows, f"After the {walk} walk the seeded member has no enrollment row at all."
        held = live_enrollments(rows, today)
        assert not held, (
            f"After the {walk} walk, a member listed with {NOT_A_STUDENT[kind]} still holds an "
            f"enrollment covering {today}: {[dict(row) for row in held]}. Closed with today is still "
            "open today — the landing and the submit path both read `ended_on >= today`."
        )


def test_a_truncated_walk_still_closes_the_enrollment_of_a_member_it_read_as_staff(
    roster_sync: Any,
    synced_section: Any,
    service_wire: Any,
    roster_rows: Any,
    seed_a_member: Any,
    application_session: Any,
    a_subject: Any,
) -> None:
    """The closing is driven by the member's own document, so a walk need not finish.

    E5.1-02's work order (D5): a teaching member's or test user's open enrollment
    is closed "on any walk, complete or not", because the walk read that member's
    roles — unlike a grant ending, which is about members a walk did *not* see.

    **The mutation this kills:** the closing gated on `complete`, which leaves a
    test user counted as a student for as long as the platform's later pages keep
    failing.
    """
    member = a_subject("read-on-the-first-page")
    seed_a_member(synced_section, member, started_on=weeks_ago(WEEKS_AGO))
    following = walk_a_synced_section(
        roster_sync,
        synced_section,
        service_wire,
        application_session,
        [roster_member(member, roles=[LEARNER_ROLE_URN, TEST_USER_ROLE_URN])],
        truncated=True,
    )
    assert urlsplit(following).path in [
        call.path for call in service_wire.calls
    ], "The walk never asked for the page that fails, so it was not truncated."
    held = live_enrollments(roster_rows.enrollments_for(member), institution_today())
    assert not held, (
        f"A truncated walk read this member as a test user and left their enrollment open: "
        f"{[dict(row) for row in held]}."
    )


# ---------------------------------------------------------------------------
# The landing.
# ---------------------------------------------------------------------------


class LaunchingMember:
    """A subject the mock platform launches, enrolled in a section a walk can reach."""

    def __init__(self, driver: Any, offer: Any, walkable: WalkableSection, subject: str) -> None:
        self.driver = driver
        self.offer = offer
        self.walkable = walkable
        self.subject = subject


def a_launching_member(
    launch_driver_in: Any,
    landing_ground: Any,
    committed_rows: Any,
    metadata_tables: dict[str, Any],
) -> LaunchingMember:
    """A learner launch, its subject enrolled for thirty days in a section made walkable.

    The enrollment is the only row that lets this subject land at all — no person,
    no assignment (ADR 0028) — so whether the launch lands as a student is a
    question about that one enrollment, which is exactly what the walk changes.
    """
    driver = launch_driver_in()
    offer = driver.offer_for_role(LEARNER_ROLE_URN)
    subject = driver.claims_of(offer).get("sub")
    assert isinstance(subject, str) and subject, "The learner launch carries no `sub`."
    platform_key = single_primary_key(require_table(metadata_tables, "lti_platform"))
    seeded = landing_ground().a_student(
        platform_id=driver.registration.platform_row[platform_key],
        subject=subject,
        on=(datetime.now(UTC) - timedelta(days=30)).date(),
    )
    walkable = WalkableSection(
        committed_rows,
        metadata_tables,
        platform_row=driver.registration.platform_row,
        deployment_key=driver.registration.deployment_row[
            single_primary_key(require_table(metadata_tables, "lti_deployment"))
        ],
        section_id=seeded["section_id"],
        label="landing",
    )
    return LaunchingMember(driver, offer, walkable, subject)


@pytest.mark.parametrize(
    "kind", ["test-user-and-learner", "instructor"], ids=["test-user", "instructor"]
)
def test_a_member_the_walk_read_as_staff_does_not_land_as_a_student(
    kind: str,
    launch_driver_in: Any,
    landing_ground: Any,
    committed_rows: Any,
    metadata_tables: dict[str, Any],
    stored_signing_key: str,
    roster_sync: Any,
    application_session: Any,
) -> None:
    """Criterion 4: "Such a person's launch does not land as STUDENT for that section."

    The subject holds one enrollment, open for thirty days, in the section the
    walk reaches, and nothing else — no person, so no assignment. The walk lists
    them as a test user (or as an instructor with no person, so no grant is
    written). Their next launch must land on E1-13's no-access page: the refusal
    itself, read off the page's own testid, not merely "somewhere other than the
    student route".

    **The mutation this kills:** the enrollment left open (today's tree), or
    closed with today. **The pair** is the next test, where the same walk lists
    the subject as a Learner and the same launch lands as a student.
    """
    member = a_launching_member(launch_driver_in, landing_ground, committed_rows, metadata_tables)
    member.walkable.walk(
        roster_sync,
        application_session,
        [roster_member(member.subject, roles=NOT_A_STUDENT[kind])],
    )

    landed, _ = member.driver.launch(member.offer)
    location = landed.headers.get("location") or ""
    assert not location.startswith(STUDENT_LANDING), (
        f"After a walk listed this subject with {NOT_A_STUDENT[kind]}, their launch landed on the "
        f"student route ({location!r}). A launch with no assignment and a live enrollment lands as "
        "STUDENT, so the enrollment was left live."
    )
    assert landed.status_code == 200 and NO_ACCESS_TESTID in landed.text, (
        f"The launch answered {landed.status_code} with a body beginning {landed.text[:300]!r}, "
        f"which is not E1-13's `{NO_ACCESS_TESTID}` page. With no assignment and no live "
        "enrollment that page is the defined answer, and anything else is a launch that failed for "
        "a reason this test is not about."
    )


def test_a_member_the_walk_read_as_a_learner_still_lands_as_a_student(
    launch_driver_in: Any,
    landing_ground: Any,
    committed_rows: Any,
    metadata_tables: dict[str, Any],
    stored_signing_key: str,
    roster_sync: Any,
    application_session: Any,
) -> None:
    """The landing pair: listed as a Learner, the same subject lands as a student.

    **The mutation this kills:** a sync that closes every enrollment it walks, or
    a landing that refuses every launch after a walk — both of which pass the test
    above. Green today.
    """
    member = a_launching_member(launch_driver_in, landing_ground, committed_rows, metadata_tables)
    member.walkable.walk(
        roster_sync, application_session, [roster_member(member.subject, roles=A_STUDENT)]
    )
    landed, _ = member.driver.launch(member.offer)
    token = session_token_at(
        landed, STUDENT_LANDING, "A launch by a subject the walk listed as a Learner"
    )
    location = landed.headers.get("location") or ""
    assert token and location.startswith(STUDENT_LANDING), (
        f"A launch by a subject the walk listed as a Learner landed at {location!r} rather than "
        f"on the student route `{STUDENT_LANDING}` with a session. A Learner keeps a live "
        "enrollment after the walk, so the launch must land as a student."
    )


# ---------------------------------------------------------------------------
# The submission.
# ---------------------------------------------------------------------------


def a_walkable_submit_world(
    world: SubmitWorld, committed_rows: Any, metadata_tables: dict[str, Any]
) -> WalkableSection:
    """Bind the submit world's section to a deployment of its own platform, and make it walkable."""
    deployment = committed_rows.seed("lti_deployment", {"lti_platform": world.platform})
    committed_rows.commit()
    return WalkableSection(
        committed_rows,
        metadata_tables,
        platform_row=world.platform,
        deployment_key=deployment[
            single_primary_key(require_table(metadata_tables, "lti_deployment"))
        ],
        section_id=world.section[world.key_of(SECTION_TABLE)],
        label="submit",
    )


@pytest.mark.parametrize(
    "kind", ["test-user-and-learner", "instructor"], ids=["test-user", "instructor"]
)
def test_a_member_the_walk_read_as_staff_is_refused_the_submission_it_could_make_before(
    kind: str,
    open_submit_tool: Any,
    submit_world: SubmitWorld,
    signed_in_student: Any,
    mock_ai_endpoint: Any,
    open_now: tuple[Any, Any],
    committed_rows: Any,
    metadata_tables: dict[str, Any],
    stored_signing_key: str,
    roster_sync: Any,
    application_session: Any,
) -> None:
    """Criterion 4: "`POST /student/submissions` refuses them" — readable before, refused after.

    One world: a section with an open window and a student enrolled since 2020.
    Before the walk their submission is accepted, which is the control that the
    session, the window and the route all work. The walk lists them as a test user
    or a teacher; their next submission is refused with the 404 a section that
    does not exist gets, byte for byte, so the refusal says nothing about the
    section.

    **The mutation this kills:** the enrollment left live (today's tree), which
    lets a preview account or an instructor write a response a student's report
    then counts. **The pair** is the next test, where the same walk lists the same
    student as a Learner and the second submission is accepted.
    """
    world = submit_world.build(opens_at=open_now[0], closes_at=open_now[1])
    walkable = a_walkable_submit_world(world, committed_rows, metadata_tables)
    student = signed_in_student(open_submit_tool(ai_base_url=mock_ai_endpoint.base_url), world)

    before = student.submit(a_valid_submission(comment=None))
    assert 200 <= before.status_code < 300, (
        f"Before any walk, a complete submission from the enrolled student answered "
        f"{before.status_code}. Body begins {before.text[:300]!r}. Until this is accepted, a "
        "refusal after the walk says nothing about the walk."
    )

    walkable.walk(
        roster_sync,
        application_session,
        [roster_member(world.student["lms_user_id"], roles=NOT_A_STUDENT[kind])],
    )

    refused = student.submit(a_valid_submission(comment=None, instructor_rating=5))
    unknown = student.submit(
        a_valid_submission(comment=None),
        section={world.key_of(SECTION_TABLE): uuid4()},
    )
    assert unknown.status_code == 404, (
        f"A section that does not exist answered {unknown.status_code}, so there is no baseline. "
        f"Body begins {unknown.text[:300]!r}."
    )
    assert refused.status_code == 404, (
        f"After a walk listed this student with {NOT_A_STUDENT[kind]}, their submission answered "
        f"{refused.status_code}. Body begins {refused.text[:300]!r}. Criterion 4: the submit path "
        "refuses a member the roster says is not a student."
    )
    assert refused.content == unknown.content, (
        f"The refusal answered {refused.content[:300]!r} and a section that does not exist "
        f"answered {unknown.content[:300]!r}; the same body keeps the refusal from naming the "
        "section."
    )


def test_a_member_the_walk_read_as_a_learner_can_still_submit(
    open_submit_tool: Any,
    submit_world: SubmitWorld,
    signed_in_student: Any,
    mock_ai_endpoint: Any,
    open_now: tuple[Any, Any],
    committed_rows: Any,
    metadata_tables: dict[str, Any],
    stored_signing_key: str,
    roster_sync: Any,
    application_session: Any,
) -> None:
    """The submission pair: listed as a Learner, the student still submits after the walk.

    **The mutation this kills:** a walk that closes every enrollment it touches,
    or a submit path that refuses everything after a sync — both pass the test
    above. Green today.
    """
    world = submit_world.build(opens_at=open_now[0], closes_at=open_now[1])
    walkable = a_walkable_submit_world(world, committed_rows, metadata_tables)
    student = signed_in_student(open_submit_tool(ai_base_url=mock_ai_endpoint.base_url), world)
    before = student.submit(a_valid_submission(comment=None))
    assert (
        200 <= before.status_code < 300
    ), f"Before any walk the submission answered {before.status_code}; this pair has no baseline."

    walkable.walk(
        roster_sync,
        application_session,
        [roster_member(world.student["lms_user_id"], roles=A_STUDENT)],
    )
    after = student.submit(a_valid_submission(comment=None, instructor_rating=5))
    assert 200 <= after.status_code < 300, (
        f"A student the walk listed as a Learner was refused their next submission: "
        f"{after.status_code}, body beginning {after.text[:300]!r}."
    )
