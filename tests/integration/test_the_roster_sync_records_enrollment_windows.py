"""What a sync writes into `enrollment` — E1-11, criteria 3 and 4.

Two columns arrive with this ticket and two that were already there change
meaning, and the whole of both criteria is about telling them apart (work order
decision D3):

  - `lms_window_start` / `lms_window_end` are **the platform's**, the ADR 0048
    extension's values verbatim, and absent when the platform supplied none. SPEC
    §3.4 is the reader: "Late adds: denominator starts at the student's first
    enrolled week (from NRPS enrollment data). Where the platform supplies no
    enrollment dates — most supply none — a student counts as enrolled from the
    section's start date". Those are two different rules and E3 can only choose
    between them if the absence was stored honestly.
  - `started_on` / `ended_on` are **Pulse's**: when a member was first and last
    seen by a sync. E0-08 created them and ADR 0023's exclusion constraint ranges
    over them, which is why a drop and a re-add are two rows rather than a status
    column.

**The roster below is composed rather than seeded, and the control that keeps
that honest is next door** —
`test_the_roster_sync_is_a_conformant_service_client.py::test_the_roster_this_suite_composes_is_the_shape_the_mock_serves`.
A static seed cannot express a member who drops on one run and returns on the
next, and AC4 is entirely about the pair of runs. The token exchange stays the
mock's throughout: only the membership document is this suite's.

**The environment** is `configured_env`'s documented values over the container's
database coordinates, laid down by `tool_doors` inside `roster_platforms`
(`docs/MISTAKES.md` entry 40). Nothing here reads `os.environ`.
"""

from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.lti]

# How far either side of UTC's own date this suite will accept "the day the sync
# ran" to be. **This suite's choice, and it is a tolerance rather than a rule**:
# nothing in E1-11 settles which zone the sync stamps `started_on` in, and the
# assertions here are about the *difference* between a platform's window value and
# Pulse's own first-seen date, which no zone can blur — every window below is
# weeks away from today.
A_DAY = timedelta(days=1)

# Where a mid-term add's window begins: three weeks ago, carried with the offset
# ADR 0048 requires ("an RFC 3339 timestamp carrying an offset, never a bare
# date"). **Not UTC**, deliberately: an offset that happens to be zero is one a
# tool can drop and still look right, and the near miss this suite is written
# around is a client that parses the instant and re-stamps it in its own zone.
WINDOW_OFFSET = "-04:00"
WEEKS_AGO = 3

# A naive timestamp — RFC 3339 shaped in every respect except that it carries no
# offset. D4: "Parse extension timestamps with offsets end to end; a naive or
# unparseable value in the extension is a per-member refusal recorded in the sync
# log line, never a synthesized value." ADR 0019 makes the column refuse it at
# bind, so a sync that passed it through would raise rather than write — which is
# the *whole roster* failing on one member's bad value, and the failure this
# ticket has to make per-member.
NAIVE_TIMESTAMP = "2026-09-08T00:00:00"


def instant(days_ago: int) -> str:
    """An RFC 3339 timestamp `days_ago` days back, carrying a non-zero offset."""
    moment = datetime.now(UTC) - timedelta(days=days_ago)
    return f"{moment.date().isoformat()}T09:30:00{WINDOW_OFFSET}"


def as_instant(value: str) -> datetime:
    """The moment an RFC 3339 timestamp names, for comparing against a stored one."""
    return datetime.fromisoformat(value)


def today_ish() -> set[date]:
    """The dates that could reasonably be called "the day this sync ran".

    A band rather than a day, for the reason `A_DAY` gives. Every assertion that
    uses it is about a value being *near now* rather than being an exact date, and
    the values it is being told apart from are weeks away.
    """
    today = datetime.now(UTC).date()
    return {today - A_DAY, today, today + A_DAY}


def one_enrollment(rows: Any, subject: str) -> Any:
    """The single enrollment row for one member, or a failure counting them."""
    found = rows.enrollments_for(subject)
    assert len(found) == 1, (
        f"The member {subject!r} has {len(found)} enrollment rows and this test is about one: "
        f"{[dict(row) for row in found]}. ADR 0023's exclusion constraint refuses two overlapping "
        "windows for one user and one section, so more than one here is either a drop and a "
        "re-add — which is a different test — or a sync writing a second row where it should have "
        "found the first."
    )
    return found[0]


@pytest.fixture
def run_a_sync(
    roster_sync: Any,
    synced_section: Any,
    service_wire: Any,
    compose_a_roster: Any,
    committed_rows: Any,
) -> Any:
    """Serve one membership container at the section's address and sync it.

    Called more than once it replaces the container and syncs again, which is what
    AC4's "across two sync runs" needs: the platform, the registration, the section
    and the token exchange are all the same, and the only thing that changed
    between the runs is the roster — exactly as it would be an hour later.
    """

    def run(members: Any, size: int = 5) -> None:
        service_wire.serve(compose_a_roster(synced_section, members, size))
        roster_sync.call(
            roster_sync.sync_one_section,
            session=committed_rows.session,
            section_id=synced_section.id,
            http=service_wire.session(),
        )
        committed_rows.commit()

    return run


def test_a_windowless_member_lands_with_an_absent_window_and_a_windowed_one_keeps_its_offset(
    run_a_sync: Any, roster_rows: Any, roster_contract: Any, a_subject: Any
) -> None:
    """Criterion 3, both members in one container so neither can be a mood.

    "The windowless member lands with an honest absent window; the windowed
    members carry RFC 3339 offsets end to end (naive datetimes are refused by the
    column type — ADR 0019 — so this is asserted at the boundary)."

    **The mutation this kills**: a sync that synthesizes a window when the platform
    supplies none — the sync's own date, the section's start, or `now()`. It is the
    single most natural thing to write, because a NOT NULL column would demand it,
    and it destroys the only signal §3.4's late-add rule has. A synthesized value
    is indistinguishable from a real one afterwards, in the row and on every screen.

    **The near miss it must not fire on** is the windowed member beside it: a sync
    that stored NULL for *everyone* would satisfy the absence half and would lose
    every real window the platform sent. Both are in the same container and both
    are asserted, so neither answer can be given twice.

    The stored instant is compared as a moment rather than as a string — the mock
    sends `-04:00` and Postgres answers in whatever the connection's zone is, and
    those are one moment written two ways (`instant_of` in
    tests/fixtures/lti_services.py says the same thing for the same reason). What
    is *not* tolerated is a naive value: ADR 0019 makes `AwareDateTime` refuse one
    at bind, so a naive datetime coming back out is the column having been declared
    as something else.
    """
    windowless = a_subject("windowless")
    windowed = a_subject("windowed")
    start = instant(WEEKS_AGO * 7)

    run_a_sync(
        [
            roster_contract.member(windowless),
            roster_contract.member(windowed, window=roster_contract.window(start, None)),
        ]
    )

    absent = one_enrollment(roster_rows, windowless)
    assert absent[roster_contract.window_start_column] is None, (
        f"The member the platform gave no enrollment extension has "
        f"`{roster_contract.window_start_column}` "
        f"{absent[roster_contract.window_start_column]!r}. ADR 0048's amendment seeds exactly this "
        "member — 'a student whose member document omits the key entirely rather than emitting it "
        "empty' — and SPEC §3.4 has a different denominator for them: 'Where the platform supplies "
        "no enrollment dates — most supply none — a student counts as enrolled from the section's "
        "start date.' A synthesized value here makes that student indistinguishable from a dated "
        "one for the rest of the term."
    )
    assert absent[roster_contract.window_end_column] is None, (
        f"The windowless member's `{roster_contract.window_end_column}` is "
        f"{absent[roster_contract.window_end_column]!r} rather than absent."
    )
    assert absent[roster_contract.started_on_column] in today_ish(), (
        f"The windowless member's `{roster_contract.started_on_column}` is "
        f"{absent[roster_contract.started_on_column]!r}, which is not the day this sync ran. That "
        "column is Pulse's own record of when a member was first seen (D3), and §3.4's late-add "
        "rule reads it: 'a student who first appears in a roster sync later than their section's "
        "first sync counts from the week of that sync'."
    )

    carried = one_enrollment(roster_rows, windowed)
    stored = carried[roster_contract.window_start_column]
    assert isinstance(stored, datetime) and stored.tzinfo is not None, (
        f"The windowed member's `{roster_contract.window_start_column}` came back as {stored!r}, "
        "which carries no timezone. ADR 0019 refuses a naive datetime at bind precisely so this "
        "cannot happen; a naive value here means the column was declared as something other than "
        "`AwareDateTime`, and E0-06's timezone-aware calendar has a hole in it."
    )
    assert stored == as_instant(start), (
        f"The platform sent `start` {start!r} and the row carries {stored!r}. Those are different "
        "moments. A tool that read the timestamp and re-stamped it in its own zone — or dropped "
        f"the {WINDOW_OFFSET} offset — moves every late add's first enrolled week by up to a day, "
        "which moves a participation denominator."
    )


def test_a_naive_extension_value_refuses_that_member_and_not_the_rest_of_the_roster(
    run_a_sync: Any, roster_rows: Any, roster_contract: Any, a_subject: Any
) -> None:
    """Decision D4, and the near miss it sits one character away from.

    "A naive or unparseable value in the extension is a per-member refusal
    recorded in the sync log line, never a synthesized value."

    **Three shapes, and only the middle one is refused**: a member with no
    extension at all is ingested with an absent window (the test above), a member
    whose extension carries a naive timestamp is refused, and a member whose
    extension carries an offset is ingested. Reading the first and the second as
    the same thing is the mistake this pins — an absent key is the platform saying
    nothing and a naive value is the platform saying something a timezone-aware
    calendar cannot store.

    **The mutation this kills**: a sync that lets the naive value reach the column,
    where `AwareDateTime` raises (ADR 0019) and takes the whole roster's
    transaction with it. One member's bad value would then stop a section syncing
    at all, and the symptom is a class that stops updating.

    **The other mutation**: a sync that catches the raise and stores `None`, which
    is the synthesized-absence D4 forbids — the row would then claim the platform
    supplied no dates when it supplied one this tool could not read.
    """
    refused = a_subject("naive")
    accepted = a_subject("offset")
    start = instant(WEEKS_AGO * 7)

    run_a_sync(
        [
            roster_contract.member(refused, window=roster_contract.window(NAIVE_TIMESTAMP, None)),
            roster_contract.member(accepted, window=roster_contract.window(start, None)),
        ]
    )

    assert not roster_rows.enrollments_for(refused), (
        f"The member whose extension carried the naive timestamp {NAIVE_TIMESTAMP!r} was enrolled "
        f"anyway: {[dict(row) for row in roster_rows.enrollments_for(refused)]}. D4 makes that a "
        "per-member refusal and forbids the two ways round it — passing the value to a column "
        "that refuses it, which fails the whole roster, and storing an absence, which claims the "
        "platform sent no dates when it sent one nothing could read."
    )
    assert one_enrollment(roster_rows, accepted)[roster_contract.window_start_column] == as_instant(
        start
    ), (
        "The member beside the refused one was not ingested with the window the platform sent, so "
        "one member's unreadable value cost the rest of the roster. A refusal that takes the whole "
        "container with it is a section that silently stops syncing."
    )


def test_a_mid_term_adds_window_start_is_the_extensions_value_and_not_the_sync_time(
    run_a_sync: Any, roster_rows: Any, roster_contract: Any, a_subject: Any
) -> None:
    """Criterion 4's last clause, which is the one a plausible implementation gets wrong.

    "A mid-term add's window start is the extension's value, not the sync time."

    A student added in week 4 whose platform dates the enrollment is a student §3.4
    can credit from week 4. A sync that stamped `lms_window_start` with its own
    clock would produce a value that looks entirely reasonable — a real instant, in
    the right term, near the right week — and would quietly re-date every student
    the platform *did* date to whenever the tool first met them.

    **The two columns are asserted apart**, because that is the distinction D3
    settles and the reason there are four columns rather than two:
    `lms_window_start` is three weeks old because the platform said so, and
    `started_on` is today because that is when Pulse first saw this member. A sync
    that wrote one value into both passes neither assertion.
    """
    subject = a_subject("mid-term-add")
    start = instant(WEEKS_AGO * 7)

    run_a_sync([roster_contract.member(subject, window=roster_contract.window(start, None))])

    row = one_enrollment(roster_rows, subject)
    assert row[roster_contract.window_start_column] == as_instant(start), (
        f"The platform dated this enrollment {start!r} and the row carries "
        f"{row[roster_contract.window_start_column]!r}. If that is the moment the sync ran, this "
        "is the defect the criterion names: every dated late add is re-dated to whenever the tool "
        "first met them, and §3.4's 'denominator starts at the student's first enrolled week (from "
        "NRPS enrollment data)' is reading Pulse's clock instead of the platform's."
    )
    assert row[roster_contract.started_on_column] in today_ish(), (
        f"`{roster_contract.started_on_column}` is {row[roster_contract.started_on_column]!r} and "
        "this sync ran today. D3 settles these as two different facts — the platform's window and "
        "Pulse's first sighting — and a sync that wrote the extension's value into both has lost "
        "the second, which is what §3.4's fallback for an undated late add is computed from."
    )


@pytest.mark.parametrize("status", ["Inactive", "Deleted"])
def test_a_dropped_member_is_ended_at_the_platforms_end_date_and_an_active_one_is_not(
    run_a_sync: Any,
    seed_a_member: Any,
    synced_section: Any,
    roster_rows: Any,
    roster_contract: Any,
    a_subject: Any,
    status: str,
) -> None:
    """Criterion 4's drop, in both spellings NRPS 2.0 gives it, beside a member who stays.

    NRPS carries three statuses and E0-15's roster serves all three; SPEC §3.4's
    "Drops: scores stop updating" is a decision the tool can only make from them.
    `Inactive` and `Deleted` are parametrised rather than folded together because
    they are two strings and a comparison written against one of them is silently
    wrong about the other — which is the shape a sync takes when it is written
    against the seed it happened to read.

    **The end date is the platform's**, per D3: "a drop … `ended_on` = the
    extension's end date if it supplies one, else the sync's date". The extension
    here supplies one, five days ago, so a sync that stamped today would end the
    enrollment five days late and credit the student for a week they were not
    enrolled in.

    **Both members are seeded out of band, three weeks back**, and that is
    arithmetic rather than convenience: ADR 0023 also puts
    `ended_on IS NULL OR ended_on >= started_on` on this table, so a member first
    seen *today* cannot be ended last week at all and the difference between the
    platform's date and the sync's would be unaskable. It has the second effect
    entry 31 asks for — the sync is updating a row it did not write.

    **The active member beside them is the near miss.** A sync that ended every
    enrollment it saw — or that read `status` as a boolean and got the sense
    backwards — passes the drop half of this test and empties the section.
    """
    dropped = a_subject("dropped")
    stayed = a_subject("stayed")
    start = instant(WEEKS_AGO * 7)
    ended = instant(5)
    first_seen = (datetime.now(UTC) - timedelta(days=WEEKS_AGO * 7)).date()

    for subject in (dropped, stayed):
        seed_a_member(
            synced_section, subject, started_on=first_seen, window_start=as_instant(start)
        )
    assert one_enrollment(roster_rows, dropped)[roster_contract.ended_on_column] is None, (
        "The seeded enrollment already carries an end date, so the run below would be asserting "
        "nothing about the drop."
    )

    run_a_sync(
        [
            roster_contract.member(
                dropped, status=status, window=roster_contract.window(start, ended)
            ),
            roster_contract.member(stayed, window=roster_contract.window(start, None)),
        ]
    )

    closed = one_enrollment(roster_rows, dropped)
    assert closed[roster_contract.ended_on_column] == as_instant(ended).date(), (
        f"A member whose roster status became `{status}` has "
        f"`{roster_contract.ended_on_column}` {closed[roster_contract.ended_on_column]!r} and the "
        f"platform's extension ended the enrollment at {ended!r}. D3: the extension's end date is "
        "the one to record where the platform supplies one — the sync's own date is the fallback "
        "for when it does not, and using it here credits the student for the days between."
    )
    assert closed[roster_contract.window_end_column] == as_instant(ended), (
        f"`{roster_contract.window_end_column}` is {closed[roster_contract.window_end_column]!r} "
        f"and the platform sent {ended!r}. The platform's own value is stored verbatim beside "
        "Pulse's date, for the same reason the start is."
    )
    assert one_enrollment(roster_rows, stayed)[roster_contract.ended_on_column] is None, (
        "The member who is still `Active` on the roster was ended too. A sync that closes every "
        "enrollment it re-reads empties a section on its second run, and the drop half of this "
        "test cannot see it."
    )


def test_a_member_who_vanishes_from_the_roster_is_ended_at_the_syncs_own_date(
    run_a_sync: Any, roster_rows: Any, roster_contract: Any, a_subject: Any
) -> None:
    """The other half of D3's drop rule: absent from the container, and no end date to copy.

    "A drop (member absent, or NRPS `status` of `Inactive` or `Deleted`)" — and
    where the platform supplies no end date, "`ended_on` = the sync's date". A
    member who simply stops appearing is the case the extension cannot date,
    because there is no member document to carry a date.

    **The mutation this kills**: a sync that only ends an enrollment when it sees a
    non-Active status. A platform that removes a dropped student from the container
    entirely — which several do — would then leave every leaver enrolled for ever,
    and E3 would go on counting them in the denominator.

    **The near miss beside it** is the member who is still there: a sync that ended
    everyone it did not re-read *by identity* would end them too if it compared the
    wrong thing.
    """
    gone = a_subject("vanished")
    present = a_subject("present")
    start = instant(WEEKS_AGO * 7)

    run_a_sync(
        [
            roster_contract.member(gone, window=roster_contract.window(start, None)),
            roster_contract.member(present, window=roster_contract.window(start, None)),
        ]
    )
    run_a_sync([roster_contract.member(present, window=roster_contract.window(start, None))])

    closed = one_enrollment(roster_rows, gone)
    assert closed[roster_contract.ended_on_column] in today_ish(), (
        f"A member who disappeared from the roster has `{roster_contract.ended_on_column}` "
        f"{closed[roster_contract.ended_on_column]!r}. The container carries no document for them, "
        "so there is no platform date to copy and D3 makes it the sync's own day. Left open, the "
        "enrollment window never closes and §3.4's denominator keeps counting a student who left."
    )
    assert closed[roster_contract.window_end_column] is None, (
        f"`{roster_contract.window_end_column}` is {closed[roster_contract.window_end_column]!r} "
        "for a member the platform sent no document for at all. That column holds the platform's "
        "value verbatim and the platform supplied none — storing Pulse's date there is the "
        "synthesized window D3 forbids, in the one place it is easiest to reach for."
    )
    assert (
        one_enrollment(roster_rows, present)[roster_contract.ended_on_column] is None
    ), "The member still on the roster was ended alongside the one who left."


def test_a_re_add_opens_a_second_enrollment_and_leaves_the_closed_one_closed(
    run_a_sync: Any,
    seed_a_member: Any,
    synced_section: Any,
    roster_rows: Any,
    roster_contract: Any,
    a_subject: Any,
) -> None:
    """Criterion 4's whole arc — add, drop, re-add — inside what ADR 0023 permits.

    "Adds, drops, and re-adds across two sync runs produce the enrollment history
    ADR 0023 permits." That record refuses overlapping windows for one user and one
    section with a GiST exclusion constraint, and it refuses `UNIQUE (user_id,
    section_id)` by name for exactly this case: "It refuses the drop-and-re-add
    above, which the LMS sends, and E3 then cannot know the student was away for
    two weeks."

    So the history is two rows: the first closed at the platform's end date, the
    second opened when the member came back. D3 makes the open/closed rows *be* the
    recorded transition — there is no status column on `enrollment` — so this is
    also the assertion that no such column quietly appeared.

    **The mutation this kills**: a sync that reopens the closed row rather than
    inserting a second one. The member is enrolled again and the weeks they were
    away vanish from the record, which is precisely the loss ADR 0023 chose its
    constraint to prevent.

    **The mutation it survives**: an implementation that inserts the new row before
    closing the old one is refused by the exclusion constraint itself, which is
    that record's own point — the failure is a database error rather than a silent
    overlap, and this test would see it as an exception rather than as a wrong row.

    **The first enrollment is seeded out of band**, three weeks back, for the
    reason the drop test above gives: ADR 0023's check constraint refuses an end
    date earlier than the start, so a member first seen today cannot be dropped ten
    days ago and the whole arc would be unexpressible in one afternoon.
    """
    subject = a_subject("re-add")
    first_start = instant(WEEKS_AGO * 7)
    dropped_at = instant(10)
    second_start = instant(2)

    seed_a_member(
        synced_section,
        subject,
        started_on=(datetime.now(UTC) - timedelta(days=WEEKS_AGO * 7)).date(),
        window_start=as_instant(first_start),
    )
    run_a_sync(
        [
            roster_contract.member(
                subject,
                status=roster_contract.inactive,
                window=roster_contract.window(first_start, dropped_at),
            )
        ]
    )
    run_a_sync([roster_contract.member(subject, window=roster_contract.window(second_start, None))])

    history = sorted(
        roster_rows.enrollments_for(subject), key=lambda row: row[roster_contract.started_on_column]
    )
    assert len(history) == 2, (
        f"Add, drop and re-add left {len(history)} enrollment row(s): "
        f"{[dict(row) for row in history]}. ADR 0023 rejects `UNIQUE (user_id, section_id)` for "
        "this case in as many words — one row means the closed window was reopened and the weeks "
        "the student was away are gone from the record."
    )
    closed, reopened = history
    assert closed[roster_contract.ended_on_column] == as_instant(dropped_at).date(), (
        f"The first enrollment ends at {closed[roster_contract.ended_on_column]!r} and the "
        f"platform dropped the member at {dropped_at!r}. A re-add that also rewrote the closed "
        "row's end date has lost the gap."
    )
    assert (
        reopened[roster_contract.ended_on_column] is None
    ), f"The re-added enrollment is already closed ({reopened[roster_contract.ended_on_column]!r})."
    assert reopened[roster_contract.window_start_column] == as_instant(second_start), (
        f"The re-added enrollment carries `{roster_contract.window_start_column}` "
        f"{reopened[roster_contract.window_start_column]!r} and the platform's second window began "
        f"at {second_start!r}. The second row's window is the platform's second window, not a copy "
        "of the first."
    )
    assert closed[roster_contract.ended_on_column] < reopened[roster_contract.started_on_column], (
        f"The closed window ends on {closed[roster_contract.ended_on_column]!r} and the new one "
        f"starts on {reopened[roster_contract.started_on_column]!r}. ADR 0023's range is inclusive "
        "at both ends — 'a student who drops on day 30 cannot be re-added on day 30' — so these "
        "two rows overlap and the database is entitled to refuse the second."
    )
