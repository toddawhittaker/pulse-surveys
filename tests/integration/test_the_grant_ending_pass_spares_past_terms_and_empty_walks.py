"""A past term's grants, and an empty walk, are left alone — E5.1-11, criteria 2 and 3.

Criterion 2: "A complete walk that drops the instructor the day after the
section's `end_date` leaves their grant in place; the same walk on `end_date`
ends it (boundary pair)." Platforms commonly end teacher enrollments when a
course concludes, and the hourly sync walks every stored address forever, so
without this the next complete walk ends an instructor's grant on her own
past-term section and she loses her past reports. `end_date` is the section's
inclusive last day (ADR 0020): on it the pass still runs; after it, it does
nothing.

Criterion 3: "A complete walk that read zero members leaves every grant and
every open enrollment in place; a walk that read one member still ends the
others' grants (control)." An empty answer from a platform is treated as an
incomplete walk for both passes.

**"Today" is the clock service's, overridden, never the real date.** Criterion 2
is a boundary on a calendar day, so a test that set `end_date` from the system
clock would pass or fail on whichever side of midnight it ran, and a test that
pinned a literal date would rot (`docs/MISTAKES.md` entry 58's calendar trap).
E2-04 routes every scheduling read through `app.services.clock`, and the roster
sync's "first seen" day already goes through it
(`test_the_roster_sync_stamps_the_clocks_day.py`). So these tests pin the clock
with a development override five years out, read the overridden day back
through `clock.today`, and set `end_date` relative to that answer. The fixture
supplies the pretended instant; the boundary under test is computed from what the
clock service answers, not from a value this file chose (entry 30).

**The control that each walk happened** is read off the record the walk itself
leaves, never off a write the ticket leaves open: for criterion 2 a new 2xx
`nrps_call` row for the section's roster address (a past-term section still has
its enrollments closed, so it is still walked), and for criterion 3 the wire's own
record that the roster address was requested.

**Which failure a red is, at HEAD.** Every red is an assertion about a grant row
or an enrollment row. The `end_date`-day test and the one-member controls are
green at HEAD and must stay green.

Not marked `invariant`: nothing here reads a §4.1 path. These tests read
`role_assignment` and `enrollment` rows directly.
"""

from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlsplit

import pytest
from fixtures.clock import DEVELOPMENT, ENVIRONMENT_VARIABLE
from fixtures.report_api import INSTRUCTOR_ROLE
from fixtures.roster_sync import (
    ENDED_ON_COLUMN,
    LEARNER_ROLE_URN,
    roster_member,
    walk_a_synced_section,
)
from fixtures.supervision import require_table, single_primary_key

pytestmark = [pytest.mark.integration, pytest.mark.lti]

# The pretended instant. Five years out, so the day the clock answers under the
# override cannot be the real day in any zone, and a sync that read the system
# clock instead could not satisfy criterion 2's pair by coincidence.
PRETEND_NOW = datetime(2031, 3, 14, 16, 0, tzinfo=UTC)

# The widest offset any IANA zone carries, either way, for the guard that the
# override is in force.
WIDEST_ZONE_OFFSET = timedelta(hours=14)

ONE_DAY = timedelta(days=1)

# How long before a walk a seeded enrollment was opened, for criterion 3. Weeks,
# so that any close the sync could write is a legal row (`ended_on >= started_on`).
WEEKS_AGO = 3

SECTION_END_COLUMN = "end_date"
TERM_END_COLUMN = "end_date"


# ---------------------------------------------------------------------------
# Readers and builders.
# ---------------------------------------------------------------------------


def platform_of(section: Any, metadata_tables: dict[str, Any]) -> Any:
    """The registration key a `synced_section` belongs to."""
    return section.registration.platform_row[
        single_primary_key(require_table(metadata_tables, "lti_platform"))
    ]


def instructor_grants(committed_rows: Any, section_id: Any) -> dict[Any, Any]:
    """`{assignment id: person id}` for every `INSTRUCTOR` row scoped to `section_id`.

    Read on the superuser connection after ending its transaction, so a row the
    sync's connection deleted is gone from the answer. The same reader
    `test_a_complete_roster_walk_ends_the_teaching_grant_it_dropped.py` uses.
    """
    from sqlalchemy import select

    graph = committed_rows.graph
    committed_rows.session.rollback()
    table = graph.assignments
    scope = graph.scope_overrides("section", section_id)
    statement = select(table).where(table.c[graph.role_column] == graph.role_value(INSTRUCTOR_ROLE))
    for column, value in scope.items():
        statement = statement.where(table.c[column] == value)
    return {
        row[graph.assignment_key]: row[graph.person_column]
        for row in committed_rows.session.execute(statement).mappings()
    }


def a_teaching_person(
    committed_rows: Any, web_identity: Any, *, platform_id: Any, subject: str, section_id: Any
) -> Any:
    """A person, their `user` row at one registration, the link, and a grant on a section.

    Answers the grant's assignment id. The person has an LMS user deliberately: a
    grant whose person has none is ended by every complete walk (ADR 0183), so
    without one the past-term pair would be about that rule instead.
    """
    person_id = web_identity.person()
    user_id = web_identity.user(platform_id=platform_id, subject=subject)
    web_identity.link_person_to_user(person_id=person_id, user_id=user_id)
    row = committed_rows.graph.assign(INSTRUCTOR_ROLE, scope=section_id, person=person_id)
    committed_rows.commit()
    return row[committed_rows.graph.assignment_key]


def set_section_end_date(
    committed_rows: Any, metadata_tables: dict[str, Any], section_id: Any, end_date: Any
) -> None:
    """Write the section's inclusive last day. Only `end_date`: the rule reads nothing else."""
    from sqlalchemy import update

    section = require_table(metadata_tables, "section")
    committed_rows.session.execute(
        update(section)
        .where(section.c[single_primary_key(section)] == section_id)
        .values(**{SECTION_END_COLUMN: end_date})
    )
    committed_rows.commit()


def term_end_date_of(committed_rows: Any, metadata_tables: dict[str, Any], section_id: Any) -> Any:
    """The `end_date` of the term the section belongs to, followed through its foreign key."""
    from sqlalchemy import select

    section = require_table(metadata_tables, "section")
    term = require_table(metadata_tables, "term")
    # A composite key would put a second column here (ADR 0018's shape); the term's
    # own key is the one that names its row.
    term_key = single_primary_key(term)
    links = [
        key.parent.name
        for key in section.foreign_keys
        if key.column.table.name == term.name and key.column.name == term_key
    ]
    assert len(links) == 1, f"`section` has {len(links)} references to `term.{term_key}` ({links})."
    committed_rows.session.rollback()
    term_id = committed_rows.session.execute(
        select(section.c[links[0]]).where(section.c[single_primary_key(section)] == section_id)
    ).scalar_one()
    return committed_rows.session.execute(
        select(term.c[TERM_END_COLUMN]).where(term.c[single_primary_key(term)] == term_id)
    ).scalar_one()


def roster_reads(roster_rows: Any, section: Any) -> dict[Any, Any]:
    """`{call id: response code}` for every `nrps_call` row that read this section's roster."""
    path = urlsplit(section.address or "").path
    return {
        call["id"]: call.get("response_code")
        for call in roster_rows.calls_for(section.id)
        if urlsplit(call["url"]).path == path
    }


def days_a_real_clock_could_name() -> set[Any]:
    now = datetime.now(UTC)
    return {(now - WIDEST_ZONE_OFFSET).date(), now.date(), (now + WIDEST_ZONE_OFFSET).date()}


def the_clocks_day(clock_service: Any, committed_rows: Any) -> Any:
    """Today as `app.services.clock` answers it, under the settings the sync will build."""
    from app.config import Settings

    committed_rows.session.rollback()
    return clock_service.today(committed_rows.session, settings=Settings())


def pin_the_clock(
    committed_clock_overrides: Any,
    monkeypatch: pytest.MonkeyPatch,
    clock_service: Any,
    committed_rows: Any,
) -> Any:
    """Pin the clock five years out, and answer the day it now names.

    The override applies only where the environment is exactly the development
    name, so that is set first and asserted (`docs/MISTAKES.md` entry 40). The day
    is then checked to be none a real clock could name, so a sync reading the
    system clock cannot satisfy either half of the pair by the two coinciding.
    """
    monkeypatch.setenv(ENVIRONMENT_VARIABLE, DEVELOPMENT)
    committed_clock_overrides.set(pretend_now=PRETEND_NOW, anchored_at=datetime.now(UTC))
    today = the_clocks_day(clock_service, committed_rows)
    assert today not in days_a_real_clock_could_name(), (
        f"The clock service answered {today} under an override to {PRETEND_NOW!r}, which is a day "
        f"the system clock could name ({sorted(days_a_real_clock_could_name())}). The override is "
        "not in force, and this pair would be a test of the real date."
    )
    return today


# ---------------------------------------------------------------------------
# Criterion 2 — a past term's grants are left alone (boundary pair).
# ---------------------------------------------------------------------------


def walk_that_drops_the_instructor(
    *,
    days_after_end: int,
    committed_clock_overrides: Any,
    monkeypatch: pytest.MonkeyPatch,
    clock_service: Any,
    roster_sync: Any,
    synced_section: Any,
    service_wire: Any,
    committed_rows: Any,
    metadata_tables: dict[str, Any],
    roster_rows: Any,
    application_session: Any,
    web_identity: Any,
    a_subject: Any,
) -> tuple[Any, dict[Any, Any], Any]:
    """Seed an instructor, set `end_date` `days_after_end` days before today, walk without her.

    Answers the instructor's assignment id, the section's grants after the walk,
    and the day the walk ran on. Shared by both halves of the pair, so the two
    differ in exactly one number.
    """
    today = pin_the_clock(committed_clock_overrides, monkeypatch, clock_service, committed_rows)
    set_section_end_date(
        committed_rows, metadata_tables, synced_section.id, today - days_after_end * ONE_DAY
    )
    term_end = term_end_date_of(committed_rows, metadata_tables, synced_section.id)
    assert term_end < today - ONE_DAY, (
        f"The section's term ends on {term_end}, which is not before the day before the walk "
        f"({today - ONE_DAY}). Its term has to have ended on both sides of this pair, so that a "
        "rule reading the term's `end_date` instead of the section's ends nothing on either side "
        "and the `end_date`-day half catches it."
    )

    assignment = a_teaching_person(
        committed_rows,
        web_identity,
        platform_id=platform_of(synced_section, metadata_tables),
        subject=a_subject("past-term-instructor"),
        section_id=synced_section.id,
    )
    assert assignment in instructor_grants(committed_rows, synced_section.id), (
        "The instructor's grant is not on the section before the walk, so nothing below is about "
        "the walk."
    )
    reads_before = set(roster_reads(roster_rows, synced_section))

    walk_a_synced_section(
        roster_sync,
        synced_section,
        service_wire,
        application_session,
        [roster_member(a_subject("past-term-learner"), roles=[LEARNER_ROLE_URN])],
    )

    after_walk = the_clocks_day(clock_service, committed_rows)
    if after_walk != today:
        pytest.fail(
            f"The clock's day moved from {today} to {after_walk} while the walk ran, so this case "
            "did not run on the day it set up. Re-run it; this is a harness condition, not a "
            "result."
        )
    this_walk = {
        call: code
        for call, code in roster_reads(roster_rows, synced_section).items()
        if call not in reads_before
    }
    assert any(code is not None and 200 <= code < 300 for code in this_walk.values()), (
        f"The walk left no successful `nrps_call` row reading the section's roster ({this_walk}), "
        "so it never completed a read and the grant's fate below says nothing about the end date. "
        "This is the control; a red here means the test is broken."
    )
    return assignment, instructor_grants(committed_rows, synced_section.id), today


def test_a_complete_walk_the_day_after_the_section_ends_leaves_the_dropped_instructors_grant(
    committed_clock_overrides: Any,
    monkeypatch: pytest.MonkeyPatch,
    clock_service: Any,
    roster_sync: Any,
    synced_section: Any,
    service_wire: Any,
    committed_rows: Any,
    metadata_tables: dict[str, Any],
    roster_rows: Any,
    application_session: Any,
    web_identity: Any,
    a_subject: Any,
) -> None:
    """Criterion 2, the after side: today = `end_date` + 1, and the grant survives.

    **The mutations this kills:** no end-date gate at all (HEAD); a gate that
    reads the real date rather than the clock service (the real day is five years
    before this `end_date`, so the section looks current and the grant ends); and
    a gate shifted one day late (`today > end_date + 1`), which still ends the
    grant on the first day after the section.

    **Its pair** is the next test: the same walk with today = `end_date` must end
    the grant, so a gate that never ends anything cannot pass both.

    `committed_clock_overrides` is first in the signature so its teardown, which
    removes the override row, runs after the sync's own connections close.
    """
    assignment, after, today = walk_that_drops_the_instructor(
        days_after_end=1,
        committed_clock_overrides=committed_clock_overrides,
        monkeypatch=monkeypatch,
        clock_service=clock_service,
        roster_sync=roster_sync,
        synced_section=synced_section,
        service_wire=service_wire,
        committed_rows=committed_rows,
        metadata_tables=metadata_tables,
        roster_rows=roster_rows,
        application_session=application_session,
        web_identity=web_identity,
        a_subject=a_subject,
    )
    assert assignment in after, (
        f"A complete walk on {today}, the day after the section's last day "
        f"({today - ONE_DAY}), ended the grant of the instructor it no longer lists. E5.1-11: once "
        "the section has ended, the grant-ending pass does nothing — a platform ending a teacher's "
        "enrollment at course end must not take away her past reports."
    )


def test_a_complete_walk_on_the_sections_last_day_still_ends_the_dropped_instructors_grant(
    committed_clock_overrides: Any,
    monkeypatch: pytest.MonkeyPatch,
    clock_service: Any,
    roster_sync: Any,
    synced_section: Any,
    service_wire: Any,
    committed_rows: Any,
    metadata_tables: dict[str, Any],
    roster_rows: Any,
    application_session: Any,
    web_identity: Any,
    a_subject: Any,
) -> None:
    """Criterion 2, the on side: today = `end_date`, and the grant ends.

    `end_date` is the section's last day, inclusive (ADR 0020), and the ticket
    says "on `end_date` itself it still runs."

    **The mutations this kills:** the gate written with the exclusive comparison
    (`today >= end_date` skips), which leaves a removed instructor reading the
    section on its last day; a gate that reads the *term's* `end_date` — the term
    ended before this walk (asserted in the shared builder), so that gate skips
    here; and a pass that never ends any grant. Green at HEAD, which has no gate.
    """
    assignment, after, today = walk_that_drops_the_instructor(
        days_after_end=0,
        committed_clock_overrides=committed_clock_overrides,
        monkeypatch=monkeypatch,
        clock_service=clock_service,
        roster_sync=roster_sync,
        synced_section=synced_section,
        service_wire=service_wire,
        committed_rows=committed_rows,
        metadata_tables=metadata_tables,
        roster_rows=roster_rows,
        application_session=application_session,
        web_identity=web_identity,
        a_subject=a_subject,
    )
    assert assignment not in after, (
        f"A complete walk on {today}, the section's own last day, left the grant of the instructor "
        "it no longer lists. The pass is skipped only after `end_date`; on it, a removed "
        "instructor still loses the section (E5.1-11, E5.1-02 criterion 1)."
    )


# ---------------------------------------------------------------------------
# Criterion 3 — a walk that read zero members ends nothing.
# ---------------------------------------------------------------------------


def weeks_ago(weeks: int) -> Any:
    return (datetime.now(UTC) - timedelta(days=weeks * 7)).date()


class EmptyWalkWorld:
    """An instructor holding the section and a student enrolled in it, neither listed by the walk."""

    def __init__(self, instructor_assignment: Any, no_user_assignment: Any, student: str) -> None:
        self.instructor_assignment = instructor_assignment
        self.no_user_assignment = no_user_assignment
        self.student = student


def build_empty_walk_world(
    synced_section: Any,
    committed_rows: Any,
    metadata_tables: dict[str, Any],
    roster_rows: Any,
    web_identity: Any,
    seed_a_member: Any,
    a_subject: Any,
) -> EmptyWalkWorld:
    """Two grants (one person with an LMS user, one without) and an open enrollment.

    The no-user grant is there because a complete walk ends it whoever the roster
    lists (ADR 0183), so it is the grant a zero-member walk is likeliest to end.
    """
    instructor = a_teaching_person(
        committed_rows,
        web_identity,
        platform_id=platform_of(synced_section, metadata_tables),
        subject=a_subject("unlisted-instructor"),
        section_id=synced_section.id,
    )
    no_user = committed_rows.graph.assign(
        INSTRUCTOR_ROLE, scope=synced_section.id, person=web_identity.person()
    )[committed_rows.graph.assignment_key]
    committed_rows.commit()
    student = a_subject("unlisted-student")
    seed_a_member(synced_section, student, started_on=weeks_ago(WEEKS_AGO))

    grants = instructor_grants(committed_rows, synced_section.id)
    assert {instructor, no_user} <= set(
        grants
    ), f"The two grants this world seeded are not both on the section before the walk: {grants}."
    enrollments = roster_rows.enrollments_for(student)
    assert len(enrollments) == 1 and enrollments[0][ENDED_ON_COLUMN] is None, (
        f"The seeded student does not hold exactly one open enrollment before the walk: "
        f"{[dict(row) for row in enrollments]}."
    )
    return EmptyWalkWorld(instructor, no_user, student)


def assert_the_roster_was_read(service_wire: Any, synced_section: Any) -> None:
    """The control that a walk happened: the wire carried a request for the roster address."""
    path = urlsplit(synced_section.address or "").path
    assert service_wire.to(path), (
        f"The sync never requested the section's roster at {path!r}, so it did not walk and "
        "nothing below is about what a walk does. This is the control; a red here means the test "
        "is broken."
    )


def test_a_complete_walk_that_read_no_members_ends_no_teaching_grant(
    roster_sync: Any,
    synced_section: Any,
    service_wire: Any,
    committed_rows: Any,
    metadata_tables: dict[str, Any],
    roster_rows: Any,
    application_session: Any,
    web_identity: Any,
    seed_a_member: Any,
    a_subject: Any,
) -> None:
    """Criterion 3: a zero-member walk leaves every grant in place.

    The platform answers the roster address with one page, no `next` link and no
    members — a walk that is complete by every structural test and has read
    nobody.

    **The mutations this kills:** the empty walk treated as complete (HEAD), which
    ends every grant on the section in one hour; and an emptiness test that gates
    only the enrollment-closing pass and not the grant-ending one, which the next
    test's pair catches the other way round. The no-user grant kills a gate placed
    inside the per-person loop rather than on the walk, since that grant is ended
    without reference to any member.

    **The near miss it must survive** is the next-but-one test: a walk listing one
    other member still ends the absent instructor's grant, so a pass that never
    ends anything cannot satisfy both.
    """
    build_empty_walk_world(
        synced_section,
        committed_rows,
        metadata_tables,
        roster_rows,
        web_identity,
        seed_a_member,
        a_subject,
    )
    before = instructor_grants(committed_rows, synced_section.id)

    walk_a_synced_section(roster_sync, synced_section, service_wire, application_session, [])
    assert_the_roster_was_read(service_wire, synced_section)

    after = instructor_grants(committed_rows, synced_section.id)
    assert after == before, (
        f"A complete walk that read zero members changed the section's teaching grants from "
        f"{before} to {after}. E5.1-11 treats a walk that read zero members as incomplete for the "
        "grant-ending pass: it ends nothing."
    )


def test_a_complete_walk_that_read_no_members_closes_no_open_enrollment(
    roster_sync: Any,
    synced_section: Any,
    service_wire: Any,
    committed_rows: Any,
    metadata_tables: dict[str, Any],
    roster_rows: Any,
    application_session: Any,
    web_identity: Any,
    seed_a_member: Any,
    a_subject: Any,
) -> None:
    """Criterion 3: a zero-member walk leaves every open enrollment open.

    **The mutations this kills:** the empty walk treated as complete (HEAD), which
    closes every enrollment on the section and takes every student out of the
    week's respondents; and an emptiness test that gates the grant-ending pass and
    not the enrollment-closing one.

    "Open" here is `ended_on IS NULL`, exactly as seeded, and the whole row is
    compared: the ticket says such a walk "writes nothing", so a close with any
    date — today included — is a red.
    """
    world = build_empty_walk_world(
        synced_section,
        committed_rows,
        metadata_tables,
        roster_rows,
        web_identity,
        seed_a_member,
        a_subject,
    )
    before = [dict(row) for row in roster_rows.enrollments_for(world.student)]

    walk_a_synced_section(roster_sync, synced_section, service_wire, application_session, [])
    assert_the_roster_was_read(service_wire, synced_section)

    after = [dict(row) for row in roster_rows.enrollments_for(world.student)]
    assert after == before, (
        f"A complete walk that read zero members changed the absent student's enrollment from "
        f"{before} to {after}. E5.1-11 treats a walk that read zero members as incomplete for the "
        "enrollment-closing pass: it writes nothing and closes nothing."
    )


def test_a_complete_walk_that_read_one_other_member_still_ends_the_absent_instructors_grant(
    roster_sync: Any,
    synced_section: Any,
    service_wire: Any,
    committed_rows: Any,
    metadata_tables: dict[str, Any],
    roster_rows: Any,
    application_session: Any,
    web_identity: Any,
    seed_a_member: Any,
    a_subject: Any,
) -> None:
    """Criterion 3's control: one member read, and the absent instructor's grant ends.

    The same world as the zero-member test; the walk lists one Learner who is
    neither the instructor nor the seeded student.

    **The mutations this kills:** an emptiness gate that fires on too much — on
    "no listed member was already known", on "no Instructor listed", or a pass that
    no longer ends anything — each of which passes the zero-member test above. Green
    at HEAD and after the fix. (A walk listing only an Instructor still ending an
    absent co-teacher's grant is pinned by E5.1-02's
    `test_a_complete_walk_ends_only_the_grant_of_the_instructor_it_dropped`.)
    """
    world = build_empty_walk_world(
        synced_section,
        committed_rows,
        metadata_tables,
        roster_rows,
        web_identity,
        seed_a_member,
        a_subject,
    )
    walk_a_synced_section(
        roster_sync,
        synced_section,
        service_wire,
        application_session,
        [roster_member(a_subject("the-one-listed-learner"), roles=[LEARNER_ROLE_URN])],
    )
    assert_the_roster_was_read(service_wire, synced_section)

    after = instructor_grants(committed_rows, synced_section.id)
    assert world.instructor_assignment not in after, (
        f"A complete walk that read one other member left the grant of the instructor it does not "
        f"list ({world.instructor_assignment}); the section's grants are {after}. Only a walk that "
        "read zero members is treated as incomplete. This is the control; a red here means the "
        "test or the emptiness rule is too wide."
    )


def test_a_complete_walk_that_read_one_other_member_still_closes_the_absent_students_enrollment(
    roster_sync: Any,
    synced_section: Any,
    service_wire: Any,
    committed_rows: Any,
    metadata_tables: dict[str, Any],
    roster_rows: Any,
    application_session: Any,
    web_identity: Any,
    seed_a_member: Any,
    a_subject: Any,
) -> None:
    """Criterion 3's control, enrollment side: one member read, the absent student's row closes.

    A member who vanishes from a complete walk is closed with the sync's own date
    (E1-11, D3), so "closed" is read as `ended_on` no longer NULL — not as "does not
    cover today", which a close with today would fail.

    **The mutation this kills:** an emptiness gate on the enrollment-closing pass
    that fires on any walk listing no *known* member, or a closing pass removed
    outright — each of which passes the zero-member enrollment test above. Green at
    HEAD and after the fix.
    """
    world = build_empty_walk_world(
        synced_section,
        committed_rows,
        metadata_tables,
        roster_rows,
        web_identity,
        seed_a_member,
        a_subject,
    )
    walk_a_synced_section(
        roster_sync,
        synced_section,
        service_wire,
        application_session,
        [roster_member(a_subject("the-one-listed-learner"), roles=[LEARNER_ROLE_URN])],
    )
    assert_the_roster_was_read(service_wire, synced_section)

    rows = roster_rows.enrollments_for(world.student)
    assert rows, "The absent student has no enrollment row at all after the walk."
    still_open = [dict(row) for row in rows if row[ENDED_ON_COLUMN] is None]
    assert not still_open, (
        f"A complete walk that read one other member left the absent student's enrollment open: "
        f"{still_open}. Only a walk that read zero members is treated as incomplete. This is the "
        "control; a red here means the test or the emptiness rule is too wide."
    )
