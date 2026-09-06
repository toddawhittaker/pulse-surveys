"""A staff launch does not wait on a broker that is down — ticket E3-05, criterion 5.

Two records meet here and they ask for the same test.

`docs/tickets/e3/carried-from-e2.md`, "The launch-path roster enqueue still waits
six seconds on a broker that is down": "`request_section_sync` publishes on an
unbounded connection, so a staff launch whose Redis is restarting holds the
request for six seconds after the launch is already verified and committed."
**Done when:** "the bounded connection, and a test that times a staff launch
against a broker at a closed port under a stated budget." E3-05 takes that entry
— it is the ticket that adds a second enqueue to the same door — and this module
is its done-when.

E3-05's criterion 5: "The launch returns promptly with the broker at a closed
port — a timing assertion under a stated budget, for **both** the creation
enqueue and the roster enqueue, because the carried entry's done-when asks for
exactly that and both now sit on the same door."

`docs/MISTAKES.md` entry 41 is the incident both come from, and its rule names
the third of its four clauses as the one that was added after the other three
were measured and found insufficient: "publish on a connection made for the call,
with its own retries off and its socket timeouts bounded… **Time the enqueue
against a closed port rather than trusting the flags.**" A publish flag governs
the publish; the client library opens the connection under a retry policy of its
own *before* the publish is attempted.

**A budget alone would be satisfied by a launch that published nothing**, and
that is the whole difficulty of writing this test. Three separate things stop it:

  - **Both error-level records are required.** A publish that was attempted and
    refused writes one; a publish that never happened writes none. Two loggers,
    one per service, so a launch that enqueued the roster and skipped the line
    item — the state at HEAD — is red on the second and not on the first.
  - **The section is required to be in the state that qualifies for both.** It
    holds the roster address and the container address the launch advertised, and
    no line-item id: the two conditions the two triggers read. Without that, "no
    publish was attempted" would be correct behaviour rather than a defect.
  - **There is no `nrps_call` row anywhere** (`docs/MISTAKES.md` entry 7 — a
    verification window equal to the thing's own debounce proves nothing). The
    roster trigger is debounced at 300 seconds against that table; a section with
    a row inside the window skips its publish, and the timing would then be about
    a launch that published once rather than twice. The budget itself is chosen
    against the debounce rather than around it: 2.5 seconds is two orders below
    it, so nothing here can be satisfied by a debounce firing.

**The budget is SPEC §10's whole-round-trip figure**, 2.5 seconds, and what makes
it a real line rather than a generous one is the distance either side: the bounded
shape was measured at 0.037 seconds against this same closed port, and the
unbounded one this ticket removes costs roughly six seconds *per publish*. A door
carrying two unbounded publishes is about twelve.

**Predicted red, on two assertions at once, and the second is the interesting
one.** `app.services.grading` does not exist on the tree this was written
against, so no error record arrives under that logger; and `request_section_sync`
still publishes on the unbounded connection, so the elapsed time is far past the
budget before the second enqueue is even reached. Both are failed assertions
rather than errors.

**The broker is a released loopback port**, not the `.env.example` default: that
default names the Compose service `redis`, which does not resolve here, so a
publish against it waits on a name lookup whose duration belongs to the resolver
rather than to the enqueue — and a slow refusal would hide a slow enqueue.
"""

import logging
import time
from typing import Any

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.lti]

# `gradebook_door`, `a_closed_broker` and `line_item_contract` come from
# `tests/fixtures/line_item_creation.py`; `provisioning_contract`, `launch_ground`
# and `provisioned_rows` from `tests/fixtures/provisioning.py`; `roster_rows` from
# `tests/fixtures/roster_sync.py`. All are reached as fixtures rather than
# imported: an import of a fixtures module by name depends on where pytest put
# `tests/` on `sys.path`, and an import error is not a red.


def refusals_from(caplog: pytest.LogCaptureFixture, logger: str) -> list[Any]:
    """Every error-level record one service's logger wrote, its children included."""
    return [
        record
        for record in caplog.records
        if record.levelno >= logging.ERROR
        and (record.name == logger or record.name.startswith(f"{logger}."))
    ]


def everything_logged(caplog: pytest.LogCaptureFixture) -> str:
    """Every record captured, rendered, for a failure that needs to say what did happen.

    Arguments are folded in as well as the formatted message, for the reason
    `test_the_roster_sync_log_names_nobody.py` gives: a value reaches a record by
    more than one route and a check made against `record.msg` alone sees only the
    template.
    """
    lines = []
    for record in caplog.records:
        try:
            rendered = record.getMessage()
        except Exception:  # pragma: no cover - a record whose args do not match
            rendered = str(record.msg)
        lines.append(f"{record.levelname} {record.name}: {rendered}")
    return "\n".join(lines) or "(nothing was logged at all)"


def test_a_staff_launch_returns_promptly_and_attempts_both_enqueues_with_the_broker_down(
    gradebook_door: Any,
    provisioning_contract: Any,
    line_item_contract: Any,
    launch_ground: Any,
    provisioned_rows: Any,
    roster_rows: Any,
    a_closed_broker: str,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The carried entry's done-when, and criterion 5, in one measurement.

    An instructor launches a section for the first time. The launch is verified,
    the section is bound, both service addresses are stored — and then two
    enqueues are attempted against a broker that is not there. Both fail
    instantly, both say so at error level, and the person in the browser is
    answered inside SPEC §10's budget.

    **The mutation this kills**: either enqueue reverted to — or written on — the
    unbounded connection. `docs/MISTAKES.md` entry 41 records why that mutation is
    the likely one rather than an exotic one: "a new enqueue written by looking at
    the nearest example will pick up the unbounded connection, because that is what
    the launch door currently contains", which is the ticket's own second known
    trap and the reason D2 routes all three callers through one `publish_once` in
    the same change.

    **The near miss it must not fire on**: a door that enqueues nothing at all is
    the fastest door there is, and it is what the two error-record assertions
    refuse. And a door that enqueues only the roster — today's door — is refused by
    the second of them specifically, which is why the two services' loggers are
    read apart rather than together.

    **What the elapsed time covers.** The whole of `LaunchDriver.launch`: the
    login leg, the platform's mint, and the launch POST. Everything but the two
    publishes runs in this process against an in-memory platform, so a run past
    the budget is a run that waited on a socket.

    **The state the section is in is asserted before the timing is believed**, and
    it is three separate claims because the two triggers read three different
    columns between them. A section without the roster address does not qualify
    for the first publish; one without the container address does not qualify for
    the second; one already carrying a line-item id does not qualify for the
    second either. Any of the three would make "no publish was attempted" the
    correct answer, and the budget would then be measuring a door that did nothing.
    """
    door = gradebook_door(**{line_item_contract.redis_url_variable: a_closed_broker})
    offer = door.instructor_offer(provisioning_contract)
    label = provisioning_contract.label_of(door.driver.claims_of(offer))
    launch_ground(label)

    existing = [dict(row) for row in roster_rows.calls()]
    assert not existing, (
        f"There are `nrps_call` rows before this launch: {existing}. The roster trigger is "
        f"debounced against that table at {line_item_contract.debounce_seconds} seconds, so a row "
        "inside the window makes the launch skip its roster publish — and the timing below would "
        "then be about a door doing half the work it is being timed for (`docs/MISTAKES.md` "
        "entry 7)."
    )
    caplog.set_level(logging.DEBUG)
    caplog.set_level(logging.DEBUG, logger=line_item_contract.roster_sync_logger)
    caplog.set_level(logging.DEBUG, logger=line_item_contract.grading_logger)

    started = time.perf_counter()
    response, signed = door.driver.launch(offer)
    elapsed = time.perf_counter() - started

    door.driver.accepted(response, "an instructor's launch with the broker at a closed port")
    sections = [
        row
        for row in provisioned_rows.sections()
        if row.get(provisioning_contract.section_code_column) == label.code
    ]
    assert len(sections) == 1, (
        f"There are {len(sections)} sections coded {label.code!r} after this launch: "
        f"{[dict(row) for row in sections]}. With none, nothing on this door had a section to "
        "enqueue anything for and the measurement below is of a launch that was never asked to "
        "publish."
    )
    section = sections[0]
    assert section.get(provisioning_contract.section_address_column), (
        "The section holds no roster address, so §7.3's launch trigger has nothing to sync and "
        "the roster publish this test is timing was never due."
    )
    assert section.get(line_item_contract.container_column), (
        "The section holds no AGS container address, so E3-05's trigger correctly enqueues "
        "nothing and the second publish this test is timing was never due. E3-02 stores that "
        "address; `test_a_launch_stores_the_gradebook_address_it_was_given.py` is where its "
        "absence is diagnosed."
    )
    assert section.get(line_item_contract.line_item_column) is None, (
        "The section already carries a line-item id, so the creation trigger correctly enqueues "
        "nothing (D5) and the second publish was never due. This is a first launch; a value here "
        "means something wrote the column before anything created a line item."
    )
    assert not roster_rows.calls_for(section[provisioned_rows.key("section")]), (
        "The section has `nrps_call` rows immediately after its first launch, so a sync ran — "
        "with the broker at a closed port nothing should have — and the debounce may have "
        "silently skipped the publish being timed."
    )

    roster_refusals = refusals_from(caplog, line_item_contract.roster_sync_logger)
    creation_refusals = refusals_from(caplog, line_item_contract.grading_logger)
    assert roster_refusals, (
        "No error-level record arrived under "
        f"`{line_item_contract.roster_sync_logger}`, so the roster publish either was not "
        "attempted or failed silently — and a launch that publishes nothing is trivially prompt, "
        "which would make the budget below meaningless. SPEC §7.3 makes this launch the thing "
        "that bootstraps every later sync of the section.\n\n"
        f"What was logged:\n{everything_logged(caplog)}"
    )
    assert creation_refusals, (
        "No error-level record arrived under "
        f"`{line_item_contract.grading_logger}`, so no line-item creation was published at all. "
        "That is the state at HEAD — the hook does not exist — and it is exactly the case a "
        "timing assertion on its own cannot tell from a fast one. D3 has "
        f"`{line_item_contract.request_line_item_creation}` catch broadly, log at error and "
        "answer False when a publish cannot go out.\n\n"
        f"What was logged:\n{everything_logged(caplog)}"
    )
    assert elapsed < line_item_contract.budget_seconds, (
        f"The launch took {elapsed:.2f}s with the broker at a closed port, and the budget is "
        f"{line_item_contract.budget_seconds}s (SPEC §10's whole-round-trip figure). Both "
        "publishes were attempted and both were refused instantly by the operating system, so "
        "the time went on a client library's own connection retries — which is the third clause "
        "of `docs/MISTAKES.md` entry 41's rule and the six-second wait "
        "`docs/tickets/e3/carried-from-e2.md` carries into this ticket. A bounded publish against "
        "this same port was measured at 0.037s.\n\n"
        f"Roster refusals: {[record.getMessage() for record in roster_refusals]}\n"
        f"Creation refusals: {[record.getMessage() for record in creation_refusals]}"
    )
    assert signed is not None, (
        "The driver recorded no signed launch, so nothing above is about a launch this platform "
        "actually minted."
    )
