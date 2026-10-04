"""A student is a member listed as Learner and as nothing that teaches — E5.1-11, criterion 1.

"A complete walk listing a member only as `Instructor#TeachingAssistant`, and
another only as `Mentor`, gives neither a student enrollment, and closes an open
one either held before. A member listed as Learner gets one (control). A member
listed as Learner and `Instructor#TeachingAssistant` gets none."

The ticket settles the rule as an **allow-list**: a member is a student only if
the roster lists the Learner role (`…/membership#Learner`), lists neither the
Instructor role nor any Instructor sub-role (`…/membership/Instructor#…`), and is
not a test user. Before this ticket the rule was a deny-list — a student unless
the exact Instructor or TestUser URI was listed — so every other role arrived as
a student.

**Why this is a confidentiality defect and not a tidiness one.** SPEC §4's small-N
rule counts distinct student commenters, and a student enrollment is what makes a
member one of them. Four real students and a teaching assistant cross a
threshold of five and show the four students' comments. That is
`docs/MISTAKES.md` entry 50 exactly: a threshold that protects people, crossed by
a count of something else.

**Roles outside the two the ticket names** (`docs/MISTAKES.md` entry 53). A
deny-list grown by exactly the two URIs the criterion spells passes a test that
tries only those two. So the cases below include roles the criterion does not
name — ContentDeveloper, Administrator, a second Instructor sub-role (Grader),
and a URI no vocabulary defines, which carries the word `Learner` in it so a
substring match is caught too. Each falls under the settled rule's "listed only
with other roles", so each is the ticket's own sentence and none is a choice made
here.

**Every walk serves a plain Learner beside the member under test**, and that
Learner must hold an open enrollment afterwards. That is the control that the
walk ingested at all: without it, "no enrollment" would hold for a sync that
wrote nothing (`docs/MISTAKES.md` entry 3).

**What "no student enrollment" means here** is the reading E5.1-02's suite uses:
no enrollment row that covers today (`ended_on IS NULL OR ended_on >= today`),
because that is what the landing and the submit path read. A row closed *with*
today still lets its holder answer today.

**Which failure a red is, at HEAD.** Every red is an assertion about enrollment
rows; nothing here imports a deliverable. The Learner controls are green at HEAD
and must stay green — a red control means this module is broken, not the code.

Not marked `invariant`: these tests read `enrollment` rows directly and drive no
§4.1 read path. E5.1-02's module
`test_teaching_members_and_test_users_hold_no_student_enrollment.py` carries the
landing and submit-path refusals for the role sets it covers.

**A unit test on `_Member.is_student` is not here.** The ticket names that
predicate but not how a `_Member` is constructed, and building one would mean
guessing the constructor of a private class this suite cannot read. The role sets
are driven through the real sync instead.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fixtures.roster_sync import (
    INSTRUCTOR_ROLE_URN,
    LEARNER_ROLE_URN,
    institution_today,
    live_enrollments,
    roster_member,
    walk_a_synced_section,
)

pytestmark = [pytest.mark.integration, pytest.mark.lti]

# The LIS v2 membership vocabulary's context roles, and its Instructor sub-role
# namespace. Spelled as the LIS v2 vocabulary spells them; the ticket quotes the
# first two by URI. `INSTRUCTOR_ROLE_URN` is the principal role, `…membership#Instructor`;
# a sub-role lives under a different path, `…membership/Instructor#…`, so a check
# for the principal URI alone never sees one.
MEMBERSHIP = "http://purl.imsglobal.org/vocab/lis/v2/membership"
TEACHING_ASSISTANT_ROLE_URN = f"{MEMBERSHIP}/Instructor#TeachingAssistant"
GRADER_ROLE_URN = f"{MEMBERSHIP}/Instructor#Grader"
MENTOR_ROLE_URN = f"{MEMBERSHIP}#Mentor"
CONTENT_DEVELOPER_ROLE_URN = f"{MEMBERSHIP}#ContentDeveloper"
ADMINISTRATOR_ROLE_URN = f"{MEMBERSHIP}#Administrator"

# A role no vocabulary defines. It carries the word `Learner` so that a check
# reading "any role mentioning Learner" is caught, and it is under `.invalid`
# (RFC 2606) so no platform can ever send it meaning something.
UNKNOWN_ROLE_URN = "https://pulse-roles.invalid/vocab#NotALearner"

# Every role set the settled rule says is not a student, by name. The first three
# are the criterion's own; the rest are entry 53's — roles outside the named ones.
NOT_A_STUDENT: dict[str, list[str]] = {
    "teaching-assistant-only": [TEACHING_ASSISTANT_ROLE_URN],
    "mentor-only": [MENTOR_ROLE_URN],
    "learner-and-teaching-assistant": [LEARNER_ROLE_URN, TEACHING_ASSISTANT_ROLE_URN],
    "learner-and-grader": [LEARNER_ROLE_URN, GRADER_ROLE_URN],
    "content-developer-only": [CONTENT_DEVELOPER_ROLE_URN],
    "administrator-only": [ADMINISTRATOR_ROLE_URN],
    "unknown-role-only": [UNKNOWN_ROLE_URN],
}

# The role sets whose existing open enrollment the criterion says is closed.
WAS_A_STUDENT = ["teaching-assistant-only", "mentor-only", "learner-and-teaching-assistant"]

A_STUDENT = [LEARNER_ROLE_URN]

# How long before the walk a seeded enrollment was opened. Weeks, so that closing
# it on any day up to yesterday is a legal row (`ended_on >= started_on`) and a
# close with today is distinguishable from one before it. Relative to the same
# clock `institution_today` reads, so nothing here is pinned to a calendar date.
WEEKS_AGO = 3


def weeks_ago(weeks: int) -> Any:
    return (datetime.now(UTC) - timedelta(days=weeks * 7)).date()


# ---------------------------------------------------------------------------
# A member the sync meets for the first time.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("kind", list(NOT_A_STUDENT))
def test_a_new_member_who_is_not_listed_as_a_plain_learner_gets_no_student_enrollment(
    kind: str,
    roster_sync: Any,
    synced_section: Any,
    service_wire: Any,
    roster_rows: Any,
    application_session: Any,
    a_subject: Any,
) -> None:
    """Criterion 1: neither the TA-only nor the Mentor-only member gets a student enrollment.

    One complete walk serves the member under test and a plain Learner beside
    them. The Learner must hold an open enrollment (the control that the walk
    ingested); the member under test must hold none covering today.

    **The mutations this kills, case by case:**

      - `teaching-assistant-only`, `mentor-only`: the deny-list at HEAD — a
        student unless the exact Instructor or TestUser URI is listed.
      - `learner-and-teaching-assistant`: a rule that treats any Learner role as
        decisive, and one that denies only the principal `membership#Instructor`
        URI and not its sub-roles.
      - `learner-and-grader`: a deny-list that names the TeachingAssistant
        sub-role by its full URI and no other Instructor sub-role.
      - `content-developer-only`, `administrator-only`: a deny-list widened by
        exactly the two URIs the criterion spells (entry 53, one level out).
      - `unknown-role-only`: a Learner check written as a substring match
        (`"Learner" in role`), and any deny-list at all — no list can name a role
        nobody has defined.

    **The near miss it must survive:** the plain Learner beside them. A sync that
    enrolled nobody would pass every case; the control assertion is first so that
    a red there reads as "the walk did not ingest", never as a pass.
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
        f"The plain Learner {learner!r} holds no open enrollment after the walk, so the walk did "
        "not ingest this roster and the assertion below would hold for a sync that writes nothing. "
        "This is the control; a red here means the test is broken, not the rule."
    )
    held = live_enrollments(roster_rows.enrollments_for(member), today)
    assert not held, (
        f"A member listed with roles {NOT_A_STUDENT[kind]} holds an open enrollment after the "
        f"walk: {[dict(row) for row in held]}. E5.1-11 settles that a member is a student only if "
        "the roster lists Learner and neither Instructor nor any Instructor sub-role. A student "
        "enrollment makes them one of the distinct commenters SPEC §4's threshold counts."
    )


def test_a_new_member_listed_only_as_learner_gets_a_student_enrollment(
    roster_sync: Any,
    synced_section: Any,
    service_wire: Any,
    roster_rows: Any,
    application_session: Any,
    a_subject: Any,
) -> None:
    """Criterion 1's control: "A member listed as Learner gets one."

    The only member in the walk is a plain Learner, so nothing else in the roster
    can be what made the walk ingest.

    **The mutation this kills:** an allow-list that admits nobody — a Learner check
    against the wrong URI, or a rule that denies every member — which passes every
    case above. Green at HEAD and after the fix; red only when the rule refuses
    too much.
    """
    learner = a_subject("learner-only")
    walk_a_synced_section(
        roster_sync,
        synced_section,
        service_wire,
        application_session,
        [roster_member(learner, roles=A_STUDENT)],
    )
    held = live_enrollments(roster_rows.enrollments_for(learner), institution_today())
    assert len(held) == 1, (
        f"A member listed only as Learner holds {len(held)} open enrollments after a complete "
        f"walk ({[dict(row) for row in held]}); the criterion's control is exactly one."
    )


def test_a_new_member_listed_as_learner_and_mentor_is_still_a_student(
    roster_sync: Any,
    synced_section: Any,
    service_wire: Any,
    roster_rows: Any,
    application_session: Any,
    a_subject: Any,
) -> None:
    """The allow-list's other edge: Learner plus a role that does not teach is a student.

    The settled rule denies on Instructor, an Instructor sub-role, or TestUser —
    nothing else. A member who is a Learner and also a Mentor lists Learner and
    lists nothing that teaches, so they are a student.

    **The mutation this kills:** a rule written as "a student only if the roles are
    exactly `{Learner}`", which passes every not-a-student case above and silently
    drops any real student a platform also tags with a non-teaching role. Green at
    HEAD and after the fix.
    """
    member = a_subject("learner-and-mentor")
    walk_a_synced_section(
        roster_sync,
        synced_section,
        service_wire,
        application_session,
        [roster_member(member, roles=[LEARNER_ROLE_URN, MENTOR_ROLE_URN])],
    )
    held = live_enrollments(roster_rows.enrollments_for(member), institution_today())
    assert len(held) == 1, (
        f"A member listed as Learner and Mentor holds {len(held)} open enrollments after the walk "
        f"({[dict(row) for row in held]}). E5.1-11's rule denies only Instructor, an Instructor "
        "sub-role and TestUser; Mentor is none of them, so this member is a student."
    )


def test_a_new_member_listed_as_learner_and_instructor_is_not_a_student(
    roster_sync: Any,
    synced_section: Any,
    service_wire: Any,
    roster_rows: Any,
    application_session: Any,
    a_subject: Any,
) -> None:
    """The principal Instructor role still denies under the allow-list.

    E5.1-02 already pins this case (`instructor-and-learner` in
    `test_teaching_members_and_test_users_hold_no_student_enrollment.py`); it is
    repeated here beside the sub-role cases so that one module shows the whole
    rule, and so that a rewrite that matches only `membership/Instructor#…`
    sub-roles — and forgets the principal URI, which sits on a different path —
    goes red in this module's output.

    **The mutation this kills:** the Instructor-family check written as a prefix
    match on `…/membership/Instructor`, which the principal URI
    `…/membership#Instructor` does not start with. Green at HEAD.
    """
    member = a_subject("learner-and-instructor")
    learner = a_subject("plain-learner")
    walk_a_synced_section(
        roster_sync,
        synced_section,
        service_wire,
        application_session,
        [
            roster_member(member, roles=[LEARNER_ROLE_URN, INSTRUCTOR_ROLE_URN]),
            roster_member(learner, roles=A_STUDENT),
        ],
    )
    today = institution_today()
    assert live_enrollments(
        roster_rows.enrollments_for(learner), today
    ), f"The plain Learner {learner!r} holds no open enrollment, so the walk did not ingest."
    held = live_enrollments(roster_rows.enrollments_for(member), today)
    assert not held, (
        f"A member listed as Learner and Instructor holds an open enrollment: "
        f"{[dict(row) for row in held]}. Instructor plus Learner still teaches (ADR 0183)."
    )


# ---------------------------------------------------------------------------
# A member who was a student and is not any more.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("kind", WAS_A_STUDENT)
def test_an_open_enrollment_is_closed_when_the_roster_stops_listing_its_holder_as_a_learner(
    kind: str,
    roster_sync: Any,
    synced_section: Any,
    service_wire: Any,
    roster_rows: Any,
    seed_a_member: Any,
    application_session: Any,
    a_subject: Any,
) -> None:
    """Criterion 1: "…and closes an open one either held before."

    The member was enrolled three weeks ago, out of band, and a complete walk now
    lists them with a role set that is not a student's. The ticket settles that
    their enrollment is closed "by the path E5.1-02 already uses for teachers and
    test users", which closes it so that it no longer covers today. A second walk
    must not reopen it or open another. A Learner seeded the same way and listed
    as a Learner keeps hers open across both walks (the control).

    **The mutations this kills:** the open row left alone (HEAD, for every case
    here); the new rule applied when deciding whether to *write* an enrollment but
    not when deciding whether to *close* one, so a member who was a student keeps
    answering; a close with today, which the live test still reads as open; and a
    second walk that reopens the row through the re-add path.
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
            f"After the {walk} walk the member listed as a Learner no longer holds an open "
            "enrollment, so the walk closed everybody and the assertion below proves nothing. "
            "This is the control; a red here means the test is broken."
        )
        rows = roster_rows.enrollments_for(member)
        assert rows, f"After the {walk} walk the seeded member has no enrollment row at all."
        held = live_enrollments(rows, today)
        assert not held, (
            f"After the {walk} walk, a member the roster now lists with {NOT_A_STUDENT[kind]} "
            f"still holds an enrollment covering {today}: {[dict(row) for row in held]}. E5.1-11: "
            "a member who stops being a student has their open enrollment closed by the path "
            "E5.1-02 uses for teachers and test users, which leaves it not covering today."
        )
