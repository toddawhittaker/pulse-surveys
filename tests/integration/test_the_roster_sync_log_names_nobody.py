"""The sync's log carries no member's address or subject — the boundary review's H3.

`docs/tickets/e1/boundary-review.md`: "**H3 — the roster sync's log is an untested
read path.** The one component that handles a whole section's names and email
addresses has no test of any kind over what it logs; `caplog` appears in exactly
three test modules, none of them the sync's. The code is clean today."

`boundary-fix-plan.md`, batch A item 4: "Log-scan tests over the sync: no record
under `app.services.roster_sync` ever carries a served member's name, email, or
subject — canary-shaped (the values planted, then scanned for), success and failure
paths both, since failure paths are where values get printed."

**This module is a guard rather than a red.** Nothing here is expected to fail
before the fix round's code lands, and that is the point of it: the sync handles a
whole section's addresses on a path nothing watches, and the next change to it —
this batch's own dedup rule among them — is written by somebody with no test
telling them that a member's address may not be printed. A guard is worth having
before the thing it guards moves. SPEC §10's no-PII rule is what it enforces, and
a log line is where an address goes to be copied into a ticket, a dashboard and a
retention window nobody set.

**The canaries are a subject and an address, and not a name.** ADR 0050 settles
that this platform's roster exposes an address and no name — "there is no `name`,
no `given_name`, no `family_name` — not invented ones either" — so a member document
carrying a name is a shape no platform here sends, and a test asserting that the
sync never logs one would be asserting about a value that never reached it. The
review's sentence names all three; the two that exist are planted and scanned for,
and this paragraph is the record of why the third is not (`docs/MISTAKES.md`
entry 14: an enumeration is not an impossibility, and the boundary of the search is
said out loud rather than left to look like coverage).

**Failure paths carry most of the weight**, because that is where a value gets
printed: a member the sync cannot resolve, a page that answers an error mid-walk,
and — this batch's new code — a member the platform served twice. Each plants its
canaries in front of the failure and requires that the sync's own logger says
nothing that carries them.

**The control comes first and it must be green.** A scan that has gone blind
reports every leak as absent (`docs/MISTAKES.md` entry 9: a guard nobody has
watched catch its own case is a comment), and one that reads too widely reports a
library's line as the sync's. Both directions are exercised. **A red in the control
section means these tests are broken, not the sync.**
"""

import logging
from typing import Any
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

import pytest

# `invariant` joins the list rather than replacing it: every test here is a SPEC
# §4.1 denial, and CLAUDE.md makes that pass unskippable — but
# `scripts/ci/check_invariants.py` enforces it only over tests already carrying
# the marker, so a denial module without one is not reported skipped, it is not
# reported at all. Held at module level so the module's *next* denial test
# inherits it; the rule is
# `tests/unit/test_every_confidentiality_denial_module_sits_inside_the_invariant_pass.py`.
pytestmark = [pytest.mark.invariant, pytest.mark.integration, pytest.mark.lti]

# `roster_sync`, `synced_section`, `service_wire`, `compose_a_roster`,
# `roster_contract`, `roster_rows` and `a_subject` come from
# `tests/fixtures/roster_sync.py` and are reached as fixtures rather than imported.

# The logger the sync's records arrive under: the module path D1 fixes for this
# service, which is what `logging.getLogger(__name__)` produces there, and the name
# `boundary-fix-plan.md` batch A item 4 spells.
ROSTER_SYNC_LOGGER = "app.services.roster_sync"

# A logger that is not the sync's, for the scoping half of the control.
ANOTHER_APPLICATION_LOGGER = "app.services.e1_boundary_not_the_roster_sync"

# Where a second page lives when a test needs one that fails. A path of its own, so
# that failing it does not fail the first page — `ServiceWire.failing` is keyed by
# host and path, and the section's own roster is served at the section's own path.
SECOND_PAGE_PATH = "/rosters/e1-boundary-log-scan-page-two"


def a_canary_address() -> str:
    """One address nothing else in this run uses, at a domain nothing can deliver to.

    `.invalid` is RFC 2606's reserved suffix, which is the rule every address in
    this suite's seeds and fixtures already follows, and the random half is what
    makes a hit in the log this test's own value rather than a coincidence.
    """
    return f"e1-boundary-canary-{uuid4().hex[:12]}@pulse-canary.invalid"


def capture_the_syncs_log(caplog: pytest.LogCaptureFixture) -> None:
    """Capture everything, down to DEBUG, from the sync's own logger.

    Twice over, and the second call is the one that matters. `caplog.set_level`
    with no logger sets the *root* logger and the capture handler, which is enough
    only while nothing has given `app.services.roster_sync` a level of its own: a
    logger sitting at INFO drops a DEBUG record before any handler sees it, and the
    scan would then read a leak at DEBUG as an empty log. The second call names the
    logger, and `caplog` restores both levels when the test ends.

    A leak at DEBUG is not a smaller leak. It is one nobody sees until the day an
    operator raises the level to diagnose a platform, which is the day a section's
    whole roster goes into the log.
    """
    caplog.set_level(logging.DEBUG)
    caplog.set_level(logging.DEBUG, logger=ROSTER_SYNC_LOGGER)


def sync_log_text(caplog: pytest.LogCaptureFixture) -> str:
    """Everything the sync's own loggers wrote, in every place a value can hide.

    Three places rather than one, because a value reaches a log line by three
    routes and only the first is obvious:

      - the **formatted message**, which is `%s`-interpolation already done;
      - the **arguments**, repeated as they were passed, so that a record whose
        rendered message discards what it was handed — a truncating conversion such
        as `%.0s`, a formatter that never reached it — still shows the value;
      - the **exception**, formatted as a handler would render it. This is the one
        that matters on a failure path: a database error carries the values of the
        row it refused, and `logger.exception(...)` prints the whole traceback,
        including every argument a frame was holding.

    Scoped to `app.services.roster_sync` and its children rather than to everything
    pytest captured, for the reason `application_log_text` gives next door in
    `test_web_login_door.py`: a library that echoed a URL would otherwise decide
    this module's assertions, in either direction.
    """
    written: list[str] = []
    for record in caplog.records:
        if not (
            record.name == ROSTER_SYNC_LOGGER or record.name.startswith(f"{ROSTER_SYNC_LOGGER}.")
        ):
            continue
        # A record whose arguments do not match its message raises while it is
        # formatted, and a scan that died there would report every leak as absent.
        # Belt and braces rather than a path this suite exercises: pytest's own
        # capture handler formats each record as it arrives and raises there first,
        # so such a record never reaches this list. The arguments are read either
        # way, and the control below plants a record whose rendered message
        # deliberately discards the value it was handed.
        try:
            written.append(record.getMessage())
        except Exception:
            written.append(str(record.msg))
        written.append(repr(record.args))
        if record.exc_info:
            written.append(logging.Formatter().formatException(record.exc_info))
        if record.exc_text:
            written.append(record.exc_text)
    return "\n".join(written)


def carries_nothing_of(
    caplog: pytest.LogCaptureFixture, canaries: dict[str, str], what: str
) -> None:
    """Fail if any planted value reached the sync's log, naming which one did."""
    written = sync_log_text(caplog)
    found = sorted(name for name, value in canaries.items() if value in written)
    assert not found, (
        f"The sync's own logger wrote {found} while {what}. The values planted were {canaries!r} "
        f"and the records under `{ROSTER_SYNC_LOGGER}` were:\n{written}\n\n"
        "SPEC §10 keeps personal data out of logs, and this is the component that handles a whole "
        "section's addresses: a log line is where one gets copied into a ticket, a dashboard and a "
        "retention window nobody set. The section, the call's URL and a count of members are the "
        "things this record may carry; who was on the roster is not one of them."
    )


def roster_fetched(calls: list[Any], section: Any) -> list[Any]:
    """Every GET the sync made for this section's own stored roster address."""
    path = urlsplit(section.address or "").path
    return [call for call in calls if call.method.upper() == "GET" and call.path == path]


def sync(roster_sync: Any, section: Any, wire: Any, rows: Any) -> list[Any]:
    """Run one section's sync, answering the calls it made while it ran.

    The exception, if there is one, is deliberately swallowed: what the sync does
    with a failure is the writer's (ADR 0090), and every test in this module is
    about what was *written to the log* on the way. The calls come back so that each
    test can require the sync to have actually reached the page carrying its
    canaries — without that, a sync that failed before its first request would pass
    every assertion here for having logged nothing at all (`docs/MISTAKES.md`
    entry 3).
    """
    mark = len(wire.calls)
    try:
        roster_sync.call(
            roster_sync.sync_one_section,
            session=rows.session,
            section_id=section.id,
            http=wire.session(),
        )
        rows.commit()
    except Exception:
        rows.session.rollback()
    return wire.calls[mark:]


# ---------------------------------------------------------------------------
# The control. **A red here means these tests are broken, not the sync.**
# ---------------------------------------------------------------------------


def test_the_log_scan_catches_a_canary_planted_under_the_syncs_logger_and_ignores_one_beside_it(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The instrument, in both directions, before anything is asserted with it.

    **Dies if the scan is satisfied by emptiness** — the wrong logger name, a filter
    that matches nothing, a records list nobody captured — which is the failure mode
    of every leak scan that has quietly stopped looking (`docs/MISTAKES.md` entry 9).
    Three plants are required to be found: a message that interpolated its value, an
    argument whose rendered message threw it away, and an exception's own text, which
    is the route a database error takes to a log line.

    **And dies if the scan reads too widely.** A canary logged by something that is
    not the sync is not the sync leaking it, and a scan that counted it would fail
    this module for another component's line — turning a real assertion into one
    nobody can keep green.

    **A red here means these tests are broken, not the sync.**
    """
    capture_the_syncs_log(caplog)
    interpolated = a_canary_address()
    unrendered = a_canary_address()
    raised = a_canary_address()
    elsewhere = a_canary_address()

    logging.getLogger(ROSTER_SYNC_LOGGER).warning("a line that repeats %s", interpolated)
    # A record whose rendered message throws the value away and whose arguments
    # keep it: `%.0s` is a truncating conversion, so the formatted line carries
    # nothing and `record.args` carries the address. A scan that read only the
    # message would call this clean. Logged on a child of the sync's logger, so the
    # namespace half of the scan is exercised at the same time.
    logging.getLogger(f"{ROSTER_SYNC_LOGGER}.child").warning(
        "a line that renders none of %.0s", unrendered
    )
    try:
        raise ValueError(f"a refusal carrying the row it refused: {raised}")
    except ValueError:
        logging.getLogger(ROSTER_SYNC_LOGGER).exception("the walk failed")
    logging.getLogger(ANOTHER_APPLICATION_LOGGER).warning("another component said %s", elsewhere)

    written = sync_log_text(caplog)

    for planted, how in (
        (interpolated, "interpolated into the message"),
        (unrendered, "held as an argument the rendered message threw away (`%.0s`)"),
        (raised, "carried by the exception that was logged"),
    ):
        assert planted in written, (
            f"The scan did not find {planted!r}, which was {how} under `{ROSTER_SYNC_LOGGER}`. It "
            f"read:\n{written}\n\nEvery assertion in this module that a value did *not* reach the "
            "log is worthless until this passes."
        )
    assert elsewhere not in written, (
        f"The scan found {elsewhere!r}, which was logged by `{ANOTHER_APPLICATION_LOGGER}` and not "
        "by the sync. A scan that reads every logger reports another component's line as this "
        "one's leak, and this module then fails for something it does not govern."
    )


# ---------------------------------------------------------------------------
# H3 — the success path, and the three failure paths.
# ---------------------------------------------------------------------------


def test_a_successful_sync_names_no_members_subject_or_address_in_its_log(
    roster_sync: Any,
    synced_section: Any,
    service_wire: Any,
    compose_a_roster: Any,
    committed_rows: Any,
    roster_rows: Any,
    roster_contract: Any,
    a_subject: Any,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The ordinary hour: a roster ingested, and a log that says who was on it nowhere.

    **The mutation this kills**: a line at INFO or DEBUG naming what was ingested —
    `logger.info("wrote enrollment for %s (%s)", member["user_id"], member["email"])`
    — which is the most natural line in the world to write while building an ingest
    loop, and which puts a section's whole roster into the log every hour of the
    term.

    The level is set to DEBUG deliberately: a leak nobody sees in production because
    the level is INFO is a leak on the day somebody turns DEBUG on to diagnose a
    platform.

    The ingestion is required first. A sync that wrote nothing logs nothing about
    members either, and this test would then be about a run that never happened.
    """
    capture_the_syncs_log(caplog)
    subject = a_subject("log-scan")
    address = a_canary_address()
    service_wire.serve(
        compose_a_roster(synced_section, [roster_contract.member(subject, email=address)])
    )

    sync(roster_sync, synced_section, service_wire, committed_rows)

    assert roster_rows.enrollments_for(subject), (
        f"The member {subject!r} was not ingested, so this sync did not do the thing whose log is "
        "being scanned. `test_the_roster_sync_writes_members_emails_and_the_teaching_instructor.py` "
        "is where a sync that ingests nothing is diagnosed."
    )
    carries_nothing_of(
        caplog,
        {"the member's subject": subject, "the member's address": address},
        "ingesting a roster successfully",
    )


def test_a_page_that_fails_mid_walk_names_no_members_subject_or_address_in_its_log(
    roster_sync: Any,
    synced_section: Any,
    service_wire: Any,
    compose_a_roster: Any,
    committed_rows: Any,
    roster_contract: Any,
    a_subject: Any,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A walk that had the members in hand and then met an error.

    The canaries are served on the first page and the *second* page answers 500, so
    the failure happens with a container's worth of members already held. That is
    the shape a leak takes on this path: an error handler that reports what it was
    doing when it failed, and what it was doing was ingesting these people.

    **The mutation this kills**: `logger.error("sync failed after %s", members)` or
    any handler that renders the members it had, including through an exception it
    constructed with them.

    The failing page is required to have been asked for. Without that the sync never
    reached the failure this test is named after, and a log that says nothing about
    the failure path says nothing at all.
    """
    capture_the_syncs_log(caplog)
    subject = a_subject("log-scan")
    address = a_canary_address()
    split = urlsplit(str(synced_section.address))
    following = urlunsplit((split.scheme, split.netloc, SECOND_PAGE_PATH, "", ""))
    service_wire.serve(
        compose_a_roster(
            synced_section,
            [roster_contract.member(subject, email=address)],
            next_url=following,
        )
    )
    service_wire.failing(following, 500)

    during = sync(roster_sync, synced_section, service_wire, committed_rows)

    assert roster_fetched(during, synced_section), (
        "The sync never fetched the section's own roster address, so it never held the members "
        f"whose values this test plants. It made {[call.url for call in during]}."
    )
    assert [call for call in during if call.url == following], (
        f"The sync never asked for {following!r}, the page this test fails, so the failure path it "
        f"is named after was never taken. It made {[call.url for call in during]}. The walk "
        'following a `rel="next"` header is `test_the_roster_walk_follows_the_link_header_the_'
        "platform_sent.py`'s subject; here it is the instrument."
    )
    carries_nothing_of(
        caplog,
        {"the member's subject": subject, "the member's address": address},
        "meeting a page that answered 500 part-way through the walk",
    )


def test_a_member_the_sync_cannot_resolve_names_nobody_in_its_log(
    roster_sync: Any,
    synced_section: Any,
    service_wire: Any,
    compose_a_roster: Any,
    committed_rows: Any,
    roster_contract: Any,
    a_subject: Any,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A member document the sync cannot turn into a row, beside one it can.

    NRPS 2.0 makes `user_id` the member's own identifier and the sync matches a
    member to a `user` row by it, so a member document without one cannot be
    resolved to anybody. **What the sync does with it is deliberately not asserted
    here** — skipping it and refusing the whole page are both defensible and neither
    is settled by any record this module can cite; what is asserted is that whatever
    it says about the member it could not place does not carry the member's address.

    **The mutation this kills**: `logger.warning("skipping member %r", member)` —
    the single most likely line on this path, and the one that prints the whole
    document, address included, for every member a platform serves oddly.

    A well-formed member carrying its own canaries is on the same page, so a sync
    that abandons the page still had both values in hand when it logged.
    """
    capture_the_syncs_log(caplog)
    resolvable = a_subject("log-scan")
    resolvable_address = a_canary_address()
    unresolvable_address = a_canary_address()
    unresolvable = roster_contract.member(a_subject("unresolvable"), email=unresolvable_address)
    del unresolvable[roster_contract.member_id]
    service_wire.serve(
        compose_a_roster(
            synced_section,
            [roster_contract.member(resolvable, email=resolvable_address), unresolvable],
        )
    )

    during = sync(roster_sync, synced_section, service_wire, committed_rows)

    assert roster_fetched(during, synced_section), (
        "The sync never fetched the roster carrying the member it cannot resolve, so nothing here "
        f"is about that member. It made {[call.url for call in during]}."
    )
    carries_nothing_of(
        caplog,
        {
            "the resolvable member's subject": resolvable,
            "the resolvable member's address": resolvable_address,
            "the unresolvable member's address": unresolvable_address,
        },
        "meeting a member document carrying no `user_id`",
    )


def test_the_duplicate_a_platform_serves_twice_is_noted_without_naming_them(
    roster_sync: Any,
    synced_section: Any,
    service_wire: Any,
    compose_a_roster: Any,
    committed_rows: Any,
    roster_contract: Any,
    a_subject: Any,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The guard over this batch's own new line — M2's duplicate note.

    `boundary-fix-plan.md` batch A item 2 has the sync log a duplicate, and
    `test_the_roster_sync_deduplicates_a_member_served_twice.py` asserts that the
    note exists. This is the other half of that sentence, and it is written before
    the line is: the obvious way to write it is `logger.info("duplicate member %s",
    user_id)`, and the subject key is exactly one of the three values H3 says may
    never appear.

    **The mutation this kills**: a duplicate note that names the duplicate. What the
    operator needs from that record is that *this platform re-serves members across
    its page boundary*, which is a fact about the platform; which student it was is
    not part of it.

    Whether the sync succeeds is not asserted here — that is the other module's
    criterion, and this one holds whether the duplicate is deduplicated or still
    aborts the section.
    """
    capture_the_syncs_log(caplog)
    subject = a_subject("served-twice")
    address = a_canary_address()
    member = roster_contract.member(subject, email=address)
    service_wire.serve(compose_a_roster(synced_section, [member, dict(member)], size=1))

    during = sync(roster_sync, synced_section, service_wire, committed_rows)

    assert roster_fetched(during, synced_section), (
        "The sync never fetched the roster serving the duplicate, so the path this test guards was "
        f"never taken. It made {[call.url for call in during]}."
    )
    carries_nothing_of(
        caplog,
        {"the duplicated member's subject": subject, "the duplicated member's address": address},
        "meeting the same member on two pages of one container",
    )
