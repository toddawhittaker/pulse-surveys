"""One member served on two pages is one member — the boundary review's M2.

`docs/tickets/e1/boundary-review.md`: "**M2 — no dedup across roster pages**
(`roster_sync.py`, ingest loop). Confirmed by live repro: a member re-served across
a page boundary raises `ExclusionViolation` on the enrollment-overlap constraint,
uncaught, aborting the section's whole sync."

`boundary-fix-plan.md`, batch A item 2, is what this module asserts: "Members are
deduplicated by `user_id` across the assembled pages before ingest — first
occurrence wins, a duplicate is logged — so a member re-served across a page
boundary cannot abort the section's sync. The exclusion constraint still guards
genuine overlaps."

**Why a real platform does this.** A container is paged over a collection that is
still changing: a member added, removed or re-ordered between the fetch of page one
and the fetch of page two shifts every later row by one, and the member on the
boundary is served twice. Nothing about that is a defect at the platform, and a
tool that answers it by aborting the section loses the whole class rather than the
one duplicated row.

**The control this module does not repeat.** That the database still refuses two
genuinely overlapping windows for one member and one section is asserted by
`tests/integration/test_identity_schema.py::test_overlapping_enrollments_for_one_
user_and_section_are_refused`, with its own two controls. Dedup must not be bought
by loosening ADR 0023's exclusion constraint, and that test is what says the
constraint is still there. Citing it rather than copying it keeps one assertion of
one rule (`docs/MISTAKES.md` entry 19).

**The pair inside this module** is the same two pages carrying two *different*
members. A sync that deduplicates by page position, or that throws the second page
away, satisfies every assertion about the duplicate and quietly halves every class
that pages.
"""

import logging
from typing import Any

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.lti]

# `roster_sync`, `synced_section`, `service_wire`, `compose_a_roster`,
# `roster_contract`, `roster_rows` and `a_subject` come from
# `tests/fixtures/roster_sync.py` and are reached as fixtures rather than
# imported, for the reason every module in this suite gives.

# The logger the sync's own records arrive under. `boundary-fix-plan.md` batch A
# item 4 names it — "no record under `app.services.roster_sync`" — and it is the
# module path D1 fixes for this service, which is what `logging.getLogger(__name__)`
# produces there.
ROSTER_SYNC_LOGGER = "app.services.roster_sync"

# How a record says "I met this member twice". The plan's own vocabulary — "first
# occurrence wins, a duplicate is logged" — and its shortening, because a message
# is prose and this test has no business dictating the sentence. What is asserted is
# that *a record exists saying it*: the operator-visible fact that a platform is
# re-serving members across its page boundary, which is worth knowing about a
# platform and is otherwise invisible once the sync stops failing.
DUPLICATE_SPELLINGS = ("duplicat", "dedup")


def sync(roster_sync: Any, section: Any, wire: Any, rows: Any) -> Any:
    """Run one section's sync, answering the exception it raised or `None`.

    The same shape `test_the_roster_sync_refuses_an_address_it_was_told_to_fetch.py`
    uses, and for the reason it gives: ADR 0090's consequences leave raise-or-return
    to the writer, so what a test asserts is the rows, not the control flow. Here the
    exception is the *subject* of one assertion — M2's whole finding is that a
    duplicate member aborts the section — so it is handed back rather than swallowed.
    """
    try:
        roster_sync.call(
            roster_sync.sync_one_section,
            session=rows.session,
            section_id=section.id,
            http=wire.session(),
        )
        rows.commit()
        return None
    except Exception as raised:
        rows.session.rollback()
        return raised


def two_pages(compose_a_roster: Any, section: Any, members: list[Any]) -> Any:
    """One member per page, so `members` is served across a page boundary."""
    return compose_a_roster(section, members, size=1)


def served_across_two_pages(roster: Any, subjects: list[str], contract: Any) -> None:
    """Fail unless the container really is two pages carrying `subjects` in order.

    The guard `docs/MISTAKES.md` entry 3 asks for: every assertion below is about
    what happens at a page boundary, and a container that came back on one page
    poses none of it — the duplicate would be two members in one document, which is
    a different question with a different answer.
    """
    pages = roster.pages
    assert len(pages) == len(subjects), (
        f"The composed container came back on {len(pages)} page(s) and this test needs "
        f"{len(subjects)}: {pages}. `compose_a_roster(..., size=1)` is what puts one member on "
        "each page, and without the boundary nothing here is about paging."
    )
    served = [[str(member[contract.member_id]) for member in page] for page in pages]
    assert served == [
        [subject] for subject in subjects
    ], f"The pages carry {served} and this test composed them to carry {subjects} one per page."


def duplication_notes(caplog: pytest.LogCaptureFixture) -> list[str]:
    """Every message the sync's own logger wrote that says it met a member twice.

    Scoped to `app.services.roster_sync` and its children rather than to everything
    pytest captured: a library that logged the word "duplicate" for its own reasons
    would otherwise answer this question, which is the shape of a test passing for
    an unrelated reason.
    """
    return [
        record.getMessage()
        for record in caplog.records
        if (record.name == ROSTER_SYNC_LOGGER or record.name.startswith(f"{ROSTER_SYNC_LOGGER}."))
        and any(spelling in record.getMessage().lower() for spelling in DUPLICATE_SPELLINGS)
    ]


# ---------------------------------------------------------------------------
# M2 — the same member on two pages.
# ---------------------------------------------------------------------------


def test_a_member_served_on_two_pages_syncs_to_one_open_enrollment_window(
    roster_sync: Any,
    synced_section: Any,
    service_wire: Any,
    compose_a_roster: Any,
    committed_rows: Any,
    roster_rows: Any,
    roster_contract: Any,
    a_subject: Any,
) -> None:
    """M2's finding, as the row it leaves: the sync finishes, with one window open.

    **The mutation this kills**: ingesting the assembled pages member by member with
    no `user_id` seen-set — today's loop. The second copy is written as a second
    enrollment for the same user and section, ADR 0023's GiST exclusion constraint
    refuses the overlap, and the `ExclusionViolation` is uncaught: the section's
    whole sync aborts, every member on every page is rolled back, and the next hour
    does the same thing again. A class that a platform re-serves one member of is a
    class Pulse never syncs at all.

    **The near miss it is written around**: catching the constraint violation and
    carrying on. That leaves the section's sync half-written — every member after
    the duplicate is in a transaction that was rolled back — and it makes a database
    constraint part of the ingest loop's control flow. So the assertion is the state
    afterwards, not the absence of an exception alone: exactly one *open* window, so
    that a fix which wrote the row twice and closed one of them is not mistaken for
    dedup.

    Open rather than any: a member the platform still reports as `Active` has one
    enrollment window with no end, and whatever closed history a section carries
    from earlier runs is a different criterion (`records_enrollment_windows`).
    """
    duplicated = a_subject("served-twice")
    member = roster_contract.member(duplicated)
    roster = two_pages(compose_a_roster, synced_section, [member, dict(member)])
    served_across_two_pages(roster, [duplicated, duplicated], roster_contract)
    service_wire.serve(roster)

    failure = sync(roster_sync, synced_section, service_wire, committed_rows)

    assert failure is None, (
        f"A member served on both pages of the container aborted the section's sync: {failure!r}. "
        "That is M2's live repro — the second copy is written as a second enrollment for one user "
        "and one section, and ADR 0023's exclusion constraint refuses the overlap. Nothing about a "
        "platform re-serving a member across a page boundary is a defect at the platform: the "
        "collection changes while it is paged. Members are deduplicated by `user_id` across the "
        "assembled pages before ingest."
    )
    windows = roster_rows.enrollments_for(duplicated)
    open_windows = [row for row in windows if row.get(roster_contract.ended_on_column) is None]
    assert len(open_windows) == 1, (
        f"The member served twice has {len(open_windows)} open enrollment window(s) and this "
        f"criterion is one: {[dict(row) for row in windows]}. None means the sync finished by "
        "ingesting nobody; two means the duplicate reached the database, which SPEC §3.4's "
        "'was this student enrolled in week N' has no rule for answering."
    )


def test_a_member_served_on_two_pages_leaves_a_log_record_noting_the_duplication(
    roster_sync: Any,
    synced_section: Any,
    service_wire: Any,
    compose_a_roster: Any,
    committed_rows: Any,
    roster_contract: Any,
    a_subject: Any,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The second half of the plan's sentence: "first occurrence wins, a duplicate is logged".

    Once dedup lands, a platform re-serving members is invisible — the sync
    succeeds, the roster is right, and nobody learns that this platform's paging is
    unstable. The record is the only place that fact exists.

    **The mutation this kills**: dropping the duplicate silently. Every other
    assertion in this module stays green.

    **What is asserted is the fact of a record, not its wording.** The message is
    prose and belongs to the implementer; this reads it for the plan's own word and
    its shortening, and its pair —
    `test_a_roster_with_no_duplicate_leaves_no_duplication_note` — is what stops a
    line logged unconditionally from satisfying it. If neither spelling fits the
    sentence the pull request wants, that is a dispute about this constant and not
    about the behaviour.

    **The record may not name the member**, and that is asserted next door rather
    than here, in
    `test_the_roster_sync_log_names_nobody.py::test_the_duplicate_a_platform_serves_
    twice_is_noted_without_naming_them` — one behaviour per test, and this one is
    that the note exists at all.
    """
    # Both levels: the root logger's, and the sync's own. A logger sitting at INFO
    # drops a DEBUG record before any handler sees it, and the note this test looks
    # for would then be missing for a reason that is this test's rather than the
    # sync's. `caplog` restores both when the test ends.
    caplog.set_level(logging.DEBUG)
    caplog.set_level(logging.DEBUG, logger=ROSTER_SYNC_LOGGER)
    duplicated = a_subject("served-twice")
    member = roster_contract.member(duplicated)
    roster = two_pages(compose_a_roster, synced_section, [member, dict(member)])
    served_across_two_pages(roster, [duplicated, duplicated], roster_contract)
    service_wire.serve(roster)

    sync(roster_sync, synced_section, service_wire, committed_rows)

    assert duplication_notes(caplog), (
        "The platform served one member on both pages and the sync's own logger said nothing "
        f"about it. No record under `{ROSTER_SYNC_LOGGER}` carries any of {DUPLICATE_SPELLINGS}; "
        f"the records it wrote were "
        f"{[record.getMessage() for record in caplog.records if record.name.startswith('app.')]}. "
        "The plan's sentence is 'first occurrence wins, a duplicate is logged' — once the row is "
        "deduplicated, this line is the only trace that the platform's paging is re-serving "
        "members, and an operator has no other way to learn it."
    )


def test_a_roster_with_no_duplicate_leaves_no_duplication_note(
    roster_sync: Any,
    synced_section: Any,
    service_wire: Any,
    compose_a_roster: Any,
    committed_rows: Any,
    roster_contract: Any,
    a_subject: Any,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The note's near miss: two pages, two members, and nothing to report.

    A line written on every page boundary — or on every member — satisfies the test
    above perfectly and tells an operator nothing, because it says the same thing
    about every platform. This is the half that makes the note mean what it says.

    **The mutation this kills**: logging the duplication note unconditionally, or
    keying it on something that is not the `user_id` (the page index, the member's
    position, the count of members seen).
    """
    # Both levels: the root logger's, and the sync's own. A logger sitting at INFO
    # drops a DEBUG record before any handler sees it, and the note this test looks
    # for would then be missing for a reason that is this test's rather than the
    # sync's. `caplog` restores both when the test ends.
    caplog.set_level(logging.DEBUG)
    caplog.set_level(logging.DEBUG, logger=ROSTER_SYNC_LOGGER)
    first = a_subject("page-one")
    second = a_subject("page-two")
    roster = two_pages(
        compose_a_roster,
        synced_section,
        [roster_contract.member(first), roster_contract.member(second)],
    )
    served_across_two_pages(roster, [first, second], roster_contract)
    service_wire.serve(roster)

    sync(roster_sync, synced_section, service_wire, committed_rows)

    noted = duplication_notes(caplog)
    assert not noted, (
        f"A container carrying two different members over two pages was reported as carrying a "
        f"duplicate: {noted}. Nothing was served twice — the pages carry {first!r} and {second!r} "
        "— so a note here is a note about every platform that pages, and the operator-visible "
        "fact it is supposed to carry is worthless."
    )


def test_two_distinct_members_across_a_page_boundary_are_both_ingested(
    roster_sync: Any,
    synced_section: Any,
    service_wire: Any,
    compose_a_roster: Any,
    committed_rows: Any,
    roster_rows: Any,
    roster_contract: Any,
    a_subject: Any,
) -> None:
    """M2's accepted half: dedup by `user_id` keeps every member who is not the same one.

    A sync that answered the duplicate by keeping the first page and discarding the
    second passes every assertion about the duplicate above, and halves every class
    whose roster pages. So the pair is two pages carrying two different members,
    both of whom have to arrive.

    **The mutations this kills**: deduplicating by page rather than by `user_id`;
    keying the seen-set on something every member shares (the section, the roles
    array, the status); and assembling the pages by replacing the accumulated
    members with the latest page instead of extending them.

    It is close in shape to `test_a_multipage_roster_ingests_the_member_only_the_
    last_page_holds` and is not the same test: that one walks the mock's own seeded
    container to prove the walk pages at all, and this one is the composed
    two-member boundary the dedup rule is about, so that a dedup defect fails here
    with a message about dedup.
    """
    first = a_subject("page-one")
    second = a_subject("page-two")
    roster = two_pages(
        compose_a_roster,
        synced_section,
        [roster_contract.member(first), roster_contract.member(second)],
    )
    served_across_two_pages(roster, [first, second], roster_contract)
    service_wire.serve(roster)

    failure = sync(roster_sync, synced_section, service_wire, committed_rows)

    assert failure is None, (
        f"A two-page container carrying two different members raised {failure!r}. Nothing here is "
        "duplicated: this is an ordinary paged roster."
    )
    for subject in (first, second):
        assert roster_rows.enrollments_for(subject), (
            f"{subject!r} has no enrollment after a two-page sync carrying exactly two members, "
            f"one per page. The section's enrollments are {roster_rows.enrollments()}. A rule that "
            "deduplicates by anything coarser than the member's own `user_id` drops half of every "
            "class that pages, and a short roster reads as a small section."
        )
