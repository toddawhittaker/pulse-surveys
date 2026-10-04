"""A removed instructor loses the section, and a partial walk ends nothing — E5.1-02, criteria 1 and 2.

The teaching grant is an `INSTRUCTOR` `role_assignment` row scoped to a section,
and SPEC §2.1 makes teaching instructors LMS-owned: the roster says who teaches.
Before this ticket the sync only ever *added* that row, while the read predicates
in `app.services.authz` assume a removed instructor's row is gone. So an
instructor the LMS took off a section went on reading its report.

**Two halves, and they pull in opposite directions.**

  - Criterion 1: a **complete** walk that drops a member, or drops that member's
    `membership#Instructor` role, ends their grant — and the person feels it at
    the door: `GET /instructor/sections` stops naming the section, and the
    report route answers the same 404 body as a section that does not exist.
  - Criterion 2: a **truncated** walk ends nothing. A walk that did not finish
    has learned nothing about the members it did not reach, and a platform that
    fails one page for one hour must not strip every instructor on it.

**Every walk runs on the connection production uses** (`application_session`,
`pulse_app`), never the migration owner (`docs/MISTAKES.md` entry 46). The ending
spends a grant — `EXECUTE` on the ending definer — and a suite that drove the sync
as the superuser would pass whatever `pulse_app` holds.

**The refusal is asserted, not an absence, and each refusal has its readable
control in the same world** (the ticket's known traps). The instructor holds a
second taught section the walk never touches, so her section list is never empty
for an unrelated reason, and the section the walk drops answers 200 before the
walk and the not-found body after it.

**Which failure a red is, before E5.1-02 lands.** Nothing here imports a
deliverable at module level. The criterion 1 tests go red on an assertion — the
section is still listed, the report still answers 200, the grant row is still
there. The tests that read the ended record call
`require_the_ended_teaching_grant_table` first, so its absence is a FAILED naming
the table (`docs/MISTAKES.md` entry 44). Criterion 2's tests are green today —
nothing ends any grant yet — and exist to kill the mutation that ends grants on a
walk that did not finish.

**Every walk here runs on a day the walked section has not ended.** E5.1-11
settles that no teaching grant is ended once a section has ended (`today >
section.end_date`; ADR 0183 as amended), so a walk after the section's last day
proves nothing about criterion 1, and a walk that *keeps* a grant there keeps it
for a reason unrelated to the test. The report door's world starts its clock
after the last window closes, which is the day after the taught section ends, so
those walks move the development clock into the term first, check the day the
clock now names against the section's dates, and move it back to the reading
instant before anything is read (`walk_inside_the_term`). The `synced_section`
tests run on the real clock, and their section's seeded end date is fixed; they
move the section's `end_date` past the real today instead (`keep_the_section_running`),
so they do not go red, or vacuously green, once the real calendar passes it.

Marked `invariant` at the module level: a removed instructor reading a section is
a §4.1 confidentiality failure, and a module half inside the isolated pass reads
like a module inside it.
"""

from datetime import timedelta
from typing import Any

import pytest
from fixtures.instructor_sections import SECTIONS_PATH, entries_in, section_ids_in
from fixtures.report_api import (
    AFTER_THE_LAST_WINDOW,
    CLEAR_OF_AN_OPENING,
    FULL_WEEK,
    INSTRUCTOR_ROLE,
    REPORT_OPENS_BY_TERM_WEEK,
    SECOND_TAUGHT_COHORT,
    TERM_WEEK_OF_COURSE_WEEK,
    a_section_that_does_not_exist,
)
from fixtures.roster_sync import (
    ACTIVE,
    INACTIVE,
    INSTRUCTOR_ROLE_URN,
    LEARNER_ROLE_URN,
    WalkableSection,
    ended_teaching_grants,
    institution_today,
    require_the_ended_teaching_grant_table,
    roster_member,
    walk_a_synced_section,
)
from fixtures.supervision import require_table, single_primary_key
from fixtures.survey_windows import SECTION_TABLE
from fixtures.web_identity import claims_in_session

pytestmark = [pytest.mark.integration, pytest.mark.lti, pytest.mark.invariant]

# The two ways criterion 1 says a member can stop teaching, by what the complete
# walk serves in her place. Named so a failure says which one the sync missed.
LEFT_THE_ROSTER = "left-the-roster"
LOST_THE_INSTRUCTOR_ROLE = "lost-the-instructor-role"

# When a walk over the report door's world runs: the morning course week 1's
# report opened, weeks inside the taught section's term and weeks before its last
# day. Named off this world's own calendar rather than written as a literal; the
# day it lands on is checked against the section's stored dates before any walk.
WALK_INSIDE_THE_TERM = (
    REPORT_OPENS_BY_TERM_WEEK[TERM_WEEK_OF_COURSE_WEEK[FULL_WEEK]] + CLEAR_OF_AN_OPENING
)

# How far past the real today a `synced_section`'s last day is moved. A year, so
# no run of this module can reach it.
STILL_RUNNING_FOR = timedelta(days=365)

SECTION_START_COLUMN = "start_date"
SECTION_END_COLUMN = "end_date"


# ---------------------------------------------------------------------------
# Readers.
# ---------------------------------------------------------------------------


def listed_sections(door: Any) -> list[str]:
    """The section ids her `GET /instructor/sections` names, carrying her session only."""
    with door.carrying_no_cookie():
        answered = door.tool.get(SECTIONS_PATH, headers=door.credential())
    return section_ids_in(entries_in(answered))


def instructor_grants(committed_rows: Any, section_id: Any) -> dict[Any, Any]:
    """`{assignment id: person id}` for every `INSTRUCTOR` row scoped to `section_id`.

    Read on the superuser connection after ending its transaction, so a row
    another connection deleted is gone from the answer.
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
) -> dict[str, Any]:
    """A person, their `user` row at one registration, ADR 0024's link, and a grant on a section."""
    person_id = web_identity.person()
    user_id = web_identity.user(platform_id=platform_id, subject=subject)
    web_identity.link_person_to_user(person_id=person_id, user_id=user_id)
    row = committed_rows.graph.assign(INSTRUCTOR_ROLE, scope=section_id, person=person_id)
    committed_rows.commit()
    return {
        "person_id": person_id,
        "user_id": user_id,
        "assignment_id": row[committed_rows.graph.assignment_key],
    }


def platform_of(section: Any, metadata_tables: dict[str, Any]) -> Any:
    """The registration key a `synced_section` belongs to."""
    return section.registration.platform_row[
        single_primary_key(require_table(metadata_tables, "lti_platform"))
    ]


def section_dates(committed_rows: Any, metadata_tables: dict[str, Any], section_id: Any) -> Any:
    """The section's stored `(start_date, end_date)`, read after ending the transaction."""
    from sqlalchemy import select

    section = require_table(metadata_tables, "section")
    committed_rows.session.rollback()
    return committed_rows.session.execute(
        select(section.c[SECTION_START_COLUMN], section.c[SECTION_END_COLUMN]).where(
            section.c[single_primary_key(section)] == section_id
        )
    ).one()


def keep_the_section_running(
    committed_rows: Any, metadata_tables: dict[str, Any], section_id: Any
) -> None:
    """Move a `synced_section`'s last day a year past the real today, before it is walked.

    These walks run on the real clock, and the section's seeded `end_date` is a
    fixed date. Once the real calendar passes it, E5.1-11's past-term rule leaves
    every grant alone, so a test expecting a grant to end goes red and one
    expecting grants to survive goes green for the wrong reason.
    """
    from sqlalchemy import update

    section = require_table(metadata_tables, "section")
    committed_rows.session.execute(
        update(section)
        .where(section.c[single_primary_key(section)] == section_id)
        .values(**{SECTION_END_COLUMN: institution_today() + STILL_RUNNING_FOR})
    )
    committed_rows.commit()


# ---------------------------------------------------------------------------
# The instructor at the door, with the section the walk is about made walkable.
# ---------------------------------------------------------------------------


class TeachingWorld:
    """Her door, the section a walk will drop her from, and one it never touches."""

    def __init__(
        self,
        door: Any,
        walkable: WalkableSection,
        *,
        subject: str,
        walked_section: Any,
        untouched_section: Any,
    ) -> None:
        self.door = door
        self.walkable = walkable
        self.subject = subject
        self.walked_section = walked_section
        self.untouched_section = untouched_section


def build_teaching_world(
    door: Any, committed_rows: Any, metadata_tables: dict[str, Any]
) -> TeachingWorld:
    """Plant her second taught section and make the first one walkable.

    The second section is the readable control that keeps her list non-empty:
    it carries her grant and no roster address, so no walk here can reach it.
    """
    world = door.rows.world
    key = world.key_of(SECTION_TABLE)
    untouched = world.section(SECOND_TAUGHT_COHORT)[key]
    door.graph.assign(INSTRUCTOR_ROLE, scope=untouched, person=door.person_id)
    door.commit()

    registration = door.driver.registration
    walkable = WalkableSection(
        committed_rows,
        metadata_tables,
        platform_row=registration.platform_row,
        deployment_key=registration.deployment_row[
            single_primary_key(require_table(metadata_tables, "lti_deployment"))
        ],
        section_id=door.rows.taught_section_id,
        label="taught",
    )
    subject = claims_in_session(door.token).get("sub")
    assert isinstance(subject, str) and subject, (
        "Her launched session carries no `sub`, so there is no roster member this world can "
        "list her as. E1-08 puts the verified subject on every session."
    )
    return TeachingWorld(
        door,
        walkable,
        subject=subject,
        walked_section=door.rows.taught_section_id,
        untouched_section=untouched,
    )


def assert_she_can_read(world: TeachingWorld, when: str) -> None:
    """The readable control: both sections listed, and the walked one's report answers 200."""
    listed = listed_sections(world.door)
    expected = {str(world.walked_section), str(world.untouched_section)}
    assert expected <= set(listed), (
        f"{when}, her section list names {sorted(listed)} and should name both {sorted(expected)}. "
        "Until she can read the section the walk is about, a refusal afterwards says nothing about "
        "the walk."
    )
    report = world.door.report(course_week=FULL_WEEK, section_id=world.walked_section)
    assert report.status_code == 200, (
        f"{when}, the report for the section she teaches answered {report.status_code}. Body "
        f"begins {report.text[:300]!r}."
    )


def the_clocks_day(clock_service: Any, committed_rows: Any) -> Any:
    """Today as `app.services.clock` answers it, under the settings the sync builds."""
    from app.config import Settings

    committed_rows.session.rollback()
    return clock_service.today(committed_rows.session, settings=Settings())


def walk_inside_the_term(
    world: TeachingWorld,
    members: list[Any],
    *,
    roster_sync: Any,
    application_session: Any,
    committed_rows: Any,
    metadata_tables: dict[str, Any],
    clock_service: Any,
    truncated: bool = False,
) -> None:
    """Walk the section on a day inside its term, then put the clock back where reads happen.

    The report door's world reads at `AFTER_THE_LAST_WINDOW`, which is the day
    after the taught section's last day, and E5.1-11 ends no grant on a section
    that has ended. So the walk runs at `WALK_INSIDE_THE_TERM`, through the same
    seam the door uses, and the day the clock then names is checked against the
    section's stored dates before the walk: if this world's calendar ever moves,
    the precondition fails here rather than the walk silently drifting past the
    term again (`docs/disputes/E5.1-11-01.md`).
    """
    world.door.pretend(WALK_INSIDE_THE_TERM)
    walk_day = the_clocks_day(clock_service, committed_rows)
    starts, ends = section_dates(committed_rows, metadata_tables, world.walked_section)
    assert starts <= walk_day <= ends, (
        f"The walk would run on {walk_day}, and the walked section runs {starts} to {ends}. The walk "
        "has to fall inside the section's term: after its last day E5.1-11 ends no teaching grant, "
        "so a walk there says nothing about whether a complete walk ends one."
    )
    world.walkable.walk(roster_sync, application_session, members, truncated=truncated)
    world.door.pretend(AFTER_THE_LAST_WINDOW)


# ---------------------------------------------------------------------------
# Criterion 1 — at the door.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("how", [LEFT_THE_ROSTER, LOST_THE_INSTRUCTOR_ROLE])
def test_a_complete_walk_that_stops_listing_her_as_instructor_shuts_her_out_of_the_section(
    how: str,
    report_door: Any,
    committed_rows: Any,
    metadata_tables: dict[str, Any],
    stored_signing_key: str,
    roster_sync: Any,
    roster_rows: Any,
    application_session: Any,
    a_subject: Any,
    clock_service: Any,
) -> None:
    """Criterion 1, both ways a member stops teaching, asserted as the refusal at the door.

    "A complete walk drops a member, or drops that member's `membership#Instructor`
    role. Their next `GET /instructor/sections` omits the section, and
    `GET …/report/{week}` answers the same 404 body as a section that does not
    exist."

    **Readable before, refused after, in one world.** Before the walk her list
    names the section and its report answers 200; after it the list omits it,
    still names her untouched second section (so the list is not empty for an
    unrelated reason), and the report answers 404 with exactly the bytes a section
    nobody seeded gets.

    **The mutations this kills:** a sync that never ends a grant (today's tree);
    one that ends a grant only for a member missing from the roster and not for
    one still listed without the Instructor role, which the
    `lost-the-instructor-role` case catches; and a refusal that tells a removed
    instructor the section exists — a 403, or a 404 whose body differs from an
    unknown id's.

    **The near miss it must survive:** her other section. A sync that ended every
    grant she holds, rather than the walked section's, would empty her list; the
    assertion that the untouched section is still named catches it.

    **The control that the walk happened** is the learner listed beside her, who
    must hold an enrollment afterwards: a walk that never reached ingestion would
    leave her grant in place for a reason that has nothing to do with criterion 1.

    **The walk happens inside the section's term; the reads happen after it.**
    E5.1-11 ends no teaching grant once the section has ended (ADR 0183 as
    amended), and this world reads on the day after the taught section's last day.
    An earlier version walked on that day too, by accident of the world's clock,
    and the past-term rule then correctly kept her grant
    (`docs/disputes/E5.1-11-01.md`). So the walk runs at `WALK_INSIDE_THE_TERM`,
    with the walk's day asserted to be inside the section's dates, and every read
    before and after it runs at the reading instant.
    """
    world = build_teaching_world(report_door, committed_rows, metadata_tables)
    assert_she_can_read(world, "Before the walk")

    learner = a_subject("learner-beside-her")
    members = [roster_member(learner, roles=[LEARNER_ROLE_URN])]
    if how == LOST_THE_INSTRUCTOR_ROLE:
        members.append(roster_member(world.subject, roles=[LEARNER_ROLE_URN]))
    walk_inside_the_term(
        world,
        members,
        roster_sync=roster_sync,
        application_session=application_session,
        committed_rows=committed_rows,
        metadata_tables=metadata_tables,
        clock_service=clock_service,
    )

    assert roster_rows.enrollments_for(learner), (
        f"The complete walk served {learner!r} as a learner and wrote no enrollment for them, so "
        "the sync did not ingest this roster and nothing below is about a walk that ended her grant."
    )

    listed = listed_sections(world.door)
    assert str(world.untouched_section) in listed, (
        f"After the walk her list is {sorted(listed)} and no longer names her second section, which "
        "carries no roster address and was never walked. A walk ends the grants of the section it "
        "walked and no other."
    )
    assert str(world.walked_section) not in listed, (
        f"A complete walk {how.replace('-', ' ')} and her section list still names "
        f"{world.walked_section}. SPEC §2.1 makes the teaching instructor LMS-owned: when the "
        "roster stops listing her as Instructor, the grant ends, and the list is computed from the "
        "grant."
    )

    refused = world.door.report(course_week=FULL_WEEK, section_id=world.walked_section)
    unknown = world.door.report(course_week=FULL_WEEK, section_id=a_section_that_does_not_exist())
    assert unknown.status_code == 404, (
        f"A section nobody seeded answered {unknown.status_code}, so the comparison below has no "
        f"baseline. Body begins {unknown.text[:300]!r}."
    )
    assert refused.status_code == 404, (
        f"After a complete walk {how.replace('-', ' ')}, her report for the section answered "
        f"{refused.status_code}. Body begins {refused.text[:300]!r}. A removed instructor reading "
        "the section's report is the defect this ticket closes."
    )
    assert refused.content == unknown.content, (
        f"The section she was removed from answered {refused.content[:300]!r} and a section that "
        f"does not exist answered {unknown.content[:300]!r}. Criterion 1 asks for the same 404 "
        "body: a difference tells a removed instructor which sections exist."
    )


def test_a_complete_walk_that_still_lists_her_as_instructor_leaves_the_section_readable(
    report_door: Any,
    committed_rows: Any,
    metadata_tables: dict[str, Any],
    stored_signing_key: str,
    roster_sync: Any,
    roster_rows: Any,
    application_session: Any,
    a_subject: Any,
    clock_service: Any,
) -> None:
    """Criterion 1's pair: listed as Instructor, she keeps the section.

    **The mutation this kills:** a sync that ends every teaching grant on a
    section it walks completely, whoever the roster lists — which passes the test
    above perfectly and strips every instructor of every section every hour.

    Green on today's tree, by design; it is the half that goes red when the ending
    is too wide. The walk runs inside the section's term (`walk_inside_the_term`):
    on a past-term day E5.1-11 ends nothing, so a too-wide ending would pass here.
    """
    world = build_teaching_world(report_door, committed_rows, metadata_tables)
    assert_she_can_read(world, "Before the walk")

    learner = a_subject("learner-beside-her")
    walk_inside_the_term(
        world,
        [
            roster_member(world.subject, roles=[INSTRUCTOR_ROLE_URN]),
            roster_member(learner, roles=[LEARNER_ROLE_URN]),
        ],
        roster_sync=roster_sync,
        application_session=application_session,
        committed_rows=committed_rows,
        metadata_tables=metadata_tables,
        clock_service=clock_service,
    )
    assert roster_rows.enrollments_for(learner), (
        f"The walk served {learner!r} as a learner and wrote no enrollment for them, so it never "
        "ingested this roster and the section staying readable proves nothing."
    )
    assert_she_can_read(world, "After a complete walk that still lists her as Instructor")


# ---------------------------------------------------------------------------
# Criterion 2 — a walk that did not finish ends nothing.
# ---------------------------------------------------------------------------


def test_a_truncated_walk_that_never_reached_her_leaves_the_section_readable(
    report_door: Any,
    committed_rows: Any,
    metadata_tables: dict[str, Any],
    stored_signing_key: str,
    roster_sync: Any,
    roster_rows: Any,
    application_session: Any,
    a_subject: Any,
    clock_service: Any,
) -> None:
    """Criterion 2 at the door: "A truncated walk (`complete=False`) ends no grant."

    The first page lists a learner and not her; the page after it answers 500, so
    the walk cannot finish. Her absence from what was read is not evidence that
    she left.

    **The mutation this kills:** the ending run on any walk rather than on a
    complete one — the gate on `complete` dropped, or a failed page read as the
    end of the container. Either strips every instructor of a section whose
    platform failed one page for one hour.

    **The near miss:** the walk must really have been truncated *and* really have
    ingested page one. Both are asserted, so the section staying readable is about
    the truncation rather than about a walk that never ran. The walk runs inside the
    section's term (`walk_inside_the_term`), so it is not about the past-term rule
    either.
    """
    world = build_teaching_world(report_door, committed_rows, metadata_tables)
    assert_she_can_read(world, "Before the walk")

    learner = a_subject("first-page-learner")
    walk_inside_the_term(
        world,
        [roster_member(learner, roles=[LEARNER_ROLE_URN])],
        roster_sync=roster_sync,
        application_session=application_session,
        committed_rows=committed_rows,
        metadata_tables=metadata_tables,
        clock_service=clock_service,
        truncated=True,
    )
    assert world.walkable.asked_for_the_failing_page(), (
        "The walk never asked for the page that fails, so it was not truncated and this test is "
        "about something else."
    )
    assert roster_rows.enrollments_for(learner), (
        f"The first page's learner {learner!r} has no enrollment, so the walk never ingested what it "
        "read and her grant surviving proves nothing about truncation."
    )
    assert_she_can_read(world, "After a truncated walk that never reached her")


def test_a_truncated_walk_ends_no_grant_on_the_section_it_walked(
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
    """Criterion 2 at the row: every grant on the walked section survives a truncated walk.

    Two instructors hold the section — one whose person has a `user` row the
    platform could list, one whose person has none — and the truncated walk lists
    neither. Both rows must still be there.

    **The mutation this kills:** the ending gated on something other than
    completeness — on "the walk returned members", say — which a truncated walk
    with a populated first page satisfies.
    """
    keep_the_section_running(committed_rows, metadata_tables, synced_section.id)
    platform_id = platform_of(synced_section, metadata_tables)
    listed_nowhere = a_teaching_person(
        committed_rows,
        web_identity,
        platform_id=platform_id,
        subject=a_subject("instructor-on-the-failed-page"),
        section_id=synced_section.id,
    )
    with_no_user = web_identity.person()
    no_user_row = committed_rows.graph.assign(
        INSTRUCTOR_ROLE, scope=synced_section.id, person=with_no_user
    )
    committed_rows.commit()
    before = instructor_grants(committed_rows, synced_section.id)
    assert {
        listed_nowhere["assignment_id"],
        no_user_row[committed_rows.graph.assignment_key],
    } <= set(before), f"The two grants this test seeded are not both on the section: {before}."

    learner = a_subject("first-page-learner")
    walk_a_synced_section(
        roster_sync,
        synced_section,
        service_wire,
        application_session,
        [roster_member(learner, roles=[LEARNER_ROLE_URN])],
        truncated=True,
    )
    assert roster_rows.enrollments_for(learner), (
        f"The first page's learner {learner!r} has no enrollment, so the truncated walk ingested "
        "nothing and the grants surviving proves nothing."
    )
    after = instructor_grants(committed_rows, synced_section.id)
    assert after == before, (
        f"A truncated walk changed the section's teaching grants from {before} to {after}. A walk "
        "that did not finish learned nothing about the members it did not reach (criterion 2)."
    )


# ---------------------------------------------------------------------------
# Criterion 1 at the row: whose grant ends, and what record it leaves.
# ---------------------------------------------------------------------------


def test_a_complete_walk_ends_only_the_grant_of_the_instructor_it_dropped(
    roster_sync: Any,
    synced_section: Any,
    service_wire: Any,
    committed_rows: Any,
    metadata_tables: dict[str, Any],
    application_session: Any,
    web_identity: Any,
    a_subject: Any,
) -> None:
    """Two co-teachers, one listed and one dropped, in one complete walk.

    **The mutations this kills:** ending every grant on a completely walked
    section (the kept co-teacher loses hers), and ending none (the dropped one
    keeps hers). A pair across two worlds cannot tell the first from correct
    behaviour when each world holds one instructor; one world with both can.
    """
    keep_the_section_running(committed_rows, metadata_tables, synced_section.id)
    platform_id = platform_of(synced_section, metadata_tables)
    kept_subject = a_subject("kept-instructor")
    kept = a_teaching_person(
        committed_rows,
        web_identity,
        platform_id=platform_id,
        subject=kept_subject,
        section_id=synced_section.id,
    )
    dropped = a_teaching_person(
        committed_rows,
        web_identity,
        platform_id=platform_id,
        subject=a_subject("dropped-instructor"),
        section_id=synced_section.id,
    )

    walk_a_synced_section(
        roster_sync,
        synced_section,
        service_wire,
        application_session,
        [roster_member(kept_subject, roles=[INSTRUCTOR_ROLE_URN])],
    )
    after = instructor_grants(committed_rows, synced_section.id)
    assert kept["assignment_id"] in after, (
        f"The co-teacher the complete walk still lists as Instructor lost her grant: the section's "
        f"grants are now {after}. Ending is for the member the roster dropped, never for the whole "
        "section."
    )
    assert dropped["assignment_id"] not in after, (
        f"The co-teacher the complete walk no longer lists still holds her grant "
        f"({dropped['assignment_id']}). SPEC §2.1: teaching instructors are LMS-owned, and the "
        "roster stopped naming her."
    )


def test_an_inactive_instructor_member_loses_the_grant(
    roster_sync: Any,
    synced_section: Any,
    service_wire: Any,
    committed_rows: Any,
    metadata_tables: dict[str, Any],
    application_session: Any,
    web_identity: Any,
    a_subject: Any,
) -> None:
    """A member listed with the Instructor role but status `Inactive` has been dropped.

    NRPS 2.0 keeps a dropped member in the container with status `Inactive`, and
    the sync already reads that status as a drop for an enrollment. E5.1-02's work
    order (D5) settles that a teaching grant is kept only for a member that teaches
    *and is not dropped*.

    **The mutation this kills:** the keep set built from the role alone, which
    leaves every instructor an LMS deactivated holding the section. **The pair**
    is the Active co-teacher in the same walk, who keeps hers.
    """
    keep_the_section_running(committed_rows, metadata_tables, synced_section.id)
    platform_id = platform_of(synced_section, metadata_tables)
    active_subject = a_subject("active-instructor")
    inactive_subject = a_subject("inactive-instructor")
    active = a_teaching_person(
        committed_rows,
        web_identity,
        platform_id=platform_id,
        subject=active_subject,
        section_id=synced_section.id,
    )
    inactive = a_teaching_person(
        committed_rows,
        web_identity,
        platform_id=platform_id,
        subject=inactive_subject,
        section_id=synced_section.id,
    )

    walk_a_synced_section(
        roster_sync,
        synced_section,
        service_wire,
        application_session,
        [
            roster_member(active_subject, roles=[INSTRUCTOR_ROLE_URN], status=ACTIVE),
            roster_member(inactive_subject, roles=[INSTRUCTOR_ROLE_URN], status=INACTIVE),
        ],
    )
    after = instructor_grants(committed_rows, synced_section.id)
    assert active["assignment_id"] in after, (
        f"The Active instructor lost her grant ({after}), so this walk ended grants regardless of "
        "status and the assertion below would hold for the wrong reason."
    )
    assert inactive["assignment_id"] not in after, (
        f"The member the roster lists as Instructor with status `Inactive` still holds the grant "
        f"({inactive['assignment_id']}). An Inactive member has been dropped by the platform."
    )


def test_a_complete_walk_ends_a_grant_whose_person_has_no_lms_user(
    roster_sync: Any,
    synced_section: Any,
    service_wire: Any,
    committed_rows: Any,
    metadata_tables: dict[str, Any],
    application_session: Any,
    web_identity: Any,
    a_subject: Any,
) -> None:
    """A teaching grant held by a person no roster member can ever resolve to.

    SPEC §2.1 makes teaching instructors LMS-owned, so a grant the roster cannot
    name is a grant the roster does not support. E5.1-02's work order (D5) settles
    that such a grant is ended by a complete walk.

    **The mutation this kills:** a keep set computed by mapping each *grant's*
    person to a roster member and skipping any person with no `user` row — which
    leaves a hand-planted or stale grant in place forever. **The pair** is the
    listed instructor in the same walk, who keeps hers.
    """
    keep_the_section_running(committed_rows, metadata_tables, synced_section.id)
    platform_id = platform_of(synced_section, metadata_tables)
    listed_subject = a_subject("listed-instructor")
    listed = a_teaching_person(
        committed_rows,
        web_identity,
        platform_id=platform_id,
        subject=listed_subject,
        section_id=synced_section.id,
    )
    unlisted_person = web_identity.person()
    unlisted = committed_rows.graph.assign(
        INSTRUCTOR_ROLE, scope=synced_section.id, person=unlisted_person
    )
    committed_rows.commit()

    walk_a_synced_section(
        roster_sync,
        synced_section,
        service_wire,
        application_session,
        [roster_member(listed_subject, roles=[INSTRUCTOR_ROLE_URN])],
    )
    after = instructor_grants(committed_rows, synced_section.id)
    assert listed["assignment_id"] in after, (
        f"The instructor the walk lists lost her grant ({after}), so the assertion below would hold "
        "for the wrong reason."
    )
    assert unlisted[committed_rows.graph.assignment_key] not in after, (
        f"A grant held by a person with no LMS user survived a complete walk: {after}. No roster "
        "can list that person, and SPEC §2.1 puts the teaching instructor on the LMS side."
    )


def test_the_ended_row_a_walk_writes_names_the_grant_and_the_call_that_ended_it(
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
    """Criterion 3's record, written by a real walk rather than a direct call.

    "The row names the ended assignment, the person, the section, the role, the
    day it ended, and the roster walk that ended it." The walk is named by an
    `nrps_call` row, and it has to be one this walk made and one that succeeded:
    the definer refuses to end a grant citing anything else.

    **The mutations this kills:** the sync citing a stale call (any earlier row
    for the section), a failed call, or another section's; and an ended row that
    names the wrong person or day. **The pair** is the kept co-teacher, for whom no
    row may appear.
    """
    require_the_ended_teaching_grant_table(committed_rows.session)
    keep_the_section_running(committed_rows, metadata_tables, synced_section.id)
    platform_id = platform_of(synced_section, metadata_tables)
    kept_subject = a_subject("kept-instructor")
    kept = a_teaching_person(
        committed_rows,
        web_identity,
        platform_id=platform_id,
        subject=kept_subject,
        section_id=synced_section.id,
    )
    dropped = a_teaching_person(
        committed_rows,
        web_identity,
        platform_id=platform_id,
        subject=a_subject("dropped-instructor"),
        section_id=synced_section.id,
    )
    calls_before = {row["id"] for row in roster_rows.calls_for(synced_section.id)}
    first_day = institution_today()

    walk_a_synced_section(
        roster_sync,
        synced_section,
        service_wire,
        application_session,
        [roster_member(kept_subject, roles=[INSTRUCTOR_ROLE_URN])],
    )
    last_day = institution_today()

    ended = ended_teaching_grants(committed_rows.session)
    for_kept = [row for row in ended if row["assignment_id"] == kept["assignment_id"]]
    assert not for_kept, f"The kept co-teacher has an ended row: {for_kept}."
    for_dropped = [row for row in ended if row["assignment_id"] == dropped["assignment_id"]]
    assert len(for_dropped) == 1, (
        f"The dropped co-teacher's grant left {len(for_dropped)} ended rows ({for_dropped}); "
        "criterion 3 asks for exactly one, written in the same transaction as the deletion."
    )
    row = for_dropped[0]
    assert (row["person_id"], row["section_id"], row["role"]) == (
        dropped["person_id"],
        synced_section.id,
        INSTRUCTOR_ROLE,
    ), f"The ended row names the wrong person, section or role: {row}."
    assert row["ended_on"] in {
        first_day,
        last_day,
    }, f"The ended row says the grant ended on {row['ended_on']}; the walk ran on {first_day}."
    this_walks_successes = {
        call["id"]
        for call in roster_rows.calls_for(synced_section.id)
        if call["id"] not in calls_before
        and call.get("response_code") is not None
        and 200 <= call["response_code"] < 300
    }
    assert this_walks_successes, (
        "The walk left no successful `nrps_call` row for the section, so there is no call the ended "
        "row could correctly name."
    )
    assert row["nrps_call_id"] in this_walks_successes, (
        f"The ended row names call {row['nrps_call_id']}, which is not one of this walk's successful "
        f"calls ({sorted(map(str, this_walks_successes))}). Criterion 3: the row names the roster "
        "walk that ended the grant."
    )
