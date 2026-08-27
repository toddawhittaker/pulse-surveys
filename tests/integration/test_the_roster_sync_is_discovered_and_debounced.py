"""What the schedule reaches, and what a launch trigger does twice — E1-11, D9 and SPEC §7.3.

Two rules meet in this module and both are about a section the sync should *not*
touch.

**Discovery.** "The stored address from E1-10 is the only way the scheduled job
learns a section exists; a section with no stored address is **never-synced**, a
state distinct from empty, and stays visible as such" (the ticket, from SPEC
§7.3). A section with no address is not a failure to sync — nothing can be
attempted — and §6.1's console has to be able to tell it from a section that
synced and came back empty. D9 makes `nrps_call` the record that carries the
difference: never-synced is no address **and** no call rows, synced-empty is call
rows and no enrollments.

**The debounce.** SPEC §7.3 pulls NRPS "on schedule and on launch (debounced)",
and D9 settles the window at five minutes with `nrps_call` as its memory. A launch
storm — a class of thirty opening the tool at the top of the hour — must produce
one sync rather than thirty, and a section nobody has ever synced must not be made
to wait for one.

**The environment** is `configured_env`'s documented values over the container's
database coordinates, laid down by `tool_doors` inside `roster_platforms`
(`docs/MISTAKES.md` entry 40).
"""

import importlib
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.lti]

# The debounce window, in seconds. **Settled by E1-11's work order (D9)** — "skips
# the enqueue when the section has an `nrps_call` row younger than 5 minutes
# (constant in the module, recorded in ADR 0095)" — and written here rather than
# read out of the module under test, for the reason `docs/MISTAKES.md` entry 19
# gives: a boundary compared against the implementation's own constant is a test
# that agrees with whatever number it finds.
DEBOUNCE_SECONDS = 300

# How far either side of that line the two halves of the pair sit. One second,
# because a pair at an hour and a minute is equally satisfied by a window anywhere
# between them — the same argument E1-06's lifetime bound is asserted with (300
# accepted, 301 refused).
A_SECOND = 1

# Where the launch trigger enqueues, spelled by D10: the per-section task, whose
# `delay` is what `request_section_sync` calls or does not call.
TASKS_MODULE = "app.jobs.tasks"
SECTION_TASK = "sync_section_roster"


class Enqueues:
    """Every enqueue of the per-section task, recorded instead of performed.

    **Both spellings are intercepted.** `delay(…)` and `apply_async(…)` are one
    decision written two ways, and a recorder that watched only the first would
    read a sync enqueued through the second as "not enqueued" — which is the
    answer the debounced half of the pair below asserts, so the test would pass for
    the wrong reason on every case at once (`docs/MISTAKES.md` entry 3).
    """

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.calls: list[tuple[Any, ...]] = []
        tasks = importlib.import_module(TASKS_MODULE)
        task = getattr(tasks, SECTION_TASK, None)
        if task is None:
            pytest.fail(
                f"`{TASKS_MODULE}` defines no `{SECTION_TASK}` — it defines "
                f"{sorted(name for name in vars(tasks) if not name.startswith('_'))}. E1-11's D10 "
                "puts the per-section task there, and D9 has `request_section_sync` enqueue it "
                "after a staff launch. Without it there is nothing for the debounce to skip."
            )
        for spelling in ("delay", "apply_async"):
            monkeypatch.setattr(task, spelling, self.record, raising=False)

    def record(self, *arguments: Any, **keywords: Any) -> None:
        self.calls.append((arguments, keywords))


@pytest.fixture
def enqueues(monkeypatch: pytest.MonkeyPatch) -> Enqueues:
    """The per-section task's enqueue, intercepted for the length of one test."""
    return Enqueues(monkeypatch)


@pytest.fixture
def record_a_call(committed_rows: Any, roster_rows: Any, roster_contract: Any) -> Any:
    """Put an `nrps_call` row on a section, aged by the seconds a test names.

    Seeded rather than produced by a real sync, because the subject is the
    debounce's *memory* and not its writer: a test that ran a sync to create the
    row would take however long a sync takes, and the boundary it is asking about
    is a second wide (`docs/MISTAKES.md` entry 7 — a verification window equal to
    the thing's own debounce).
    """

    def record(section_id: Any, *, seconds_ago: int) -> Any:
        row = committed_rows.seed(
            roster_contract.nrps_call_table,
            {},
            **{
                roster_rows.link(roster_contract.nrps_call_table, "section"): section_id,
                roster_contract.called_at_column: datetime.now(UTC)
                - timedelta(seconds=seconds_ago),
            },
        )
        committed_rows.commit()
        return row

    return record


def test_a_launch_trigger_is_debounced_by_a_call_inside_the_window_and_not_by_one_outside_it(
    roster_sync: Any,
    synced_section: Any,
    committed_rows: Any,
    record_a_call: Any,
    enqueues: Any,
) -> None:
    """Decision D9's window, asserted from both sides of the line and from before it.

    "Debounce: `roster_sync.request_section_sync(session, section_id)` skips the
    enqueue when the section has an `nrps_call` row younger than 5 minutes."

    **Three cases, and each one is invisible to the other two.** A section nobody
    has ever called is enqueued — without that, an implementation that never
    enqueues anything passes the debounced case and the launch trigger does
    nothing at all, for ever. A section called 299 seconds ago is skipped, which is
    the debounce doing its job. A section called 301 seconds ago is enqueued again,
    which is a debounce that expires rather than a section that syncs once and
    never again.

    **The pair sits one second either side of the line**, deliberately: a pair at
    ten seconds and an hour is satisfied by a window anywhere between them, and
    E1-06's lifetime bound is asserted the same way for the same reason.

    **The mutation this kills**: a debounce written as "skip if the section has any
    `nrps_call` row at all", which passes the 299-second case and turns every
    section in the institution into one that syncs exactly once.

    **Every case counts the recorder's calls into an integer before it acts**, and
    the first one did not until dispute E1-11-01: `never_called = enqueues.calls`
    binds the recorder's live list rather than a snapshot of it, so `record`
    appends to the very thing the assertion compares against and `n == n + 1` is
    unsatisfiable by any implementation. A `len()` is the whole repair, and it is
    the form the two cases below already used.
    """
    never_called = len(enqueues.calls)
    roster_sync.call(
        roster_sync.request_section_sync,
        session=committed_rows.session,
        section_id=synced_section.id,
    )
    assert len(enqueues.calls) == never_called + 1, (
        "A section with no `nrps_call` row at all was not enqueued. It has never been synced, so "
        "there is nothing for a debounce to be measured against — and an implementation that "
        "enqueues nothing satisfies the skipped case below while the launch trigger does nothing "
        "for ever."
    )

    record_a_call(synced_section.id, seconds_ago=DEBOUNCE_SECONDS - A_SECOND)
    before = len(enqueues.calls)
    roster_sync.call(
        roster_sync.request_section_sync,
        session=committed_rows.session,
        section_id=synced_section.id,
    )
    assert len(enqueues.calls) == before, (
        f"A section called {DEBOUNCE_SECONDS - A_SECOND} seconds ago — inside D9's "
        f"{DEBOUNCE_SECONDS}-second window — was enqueued again. SPEC §7.3 debounces the "
        "launch trigger precisely because a class of thirty opening the tool at the top of the "
        "hour would otherwise ask the platform for one roster thirty times."
    )

    record_a_call(synced_section.id, seconds_ago=DEBOUNCE_SECONDS + A_SECOND)
    before = len(enqueues.calls)
    roster_sync.call(
        roster_sync.request_section_sync,
        session=committed_rows.session,
        section_id=synced_section.id,
    )
    assert len(enqueues.calls) == before + 1, (
        f"A section whose most recent call was {DEBOUNCE_SECONDS + A_SECOND} seconds ago — one "
        f"second past D9's {DEBOUNCE_SECONDS}-second window — was not enqueued. A debounce that "
        "never expires is a section that syncs once and then only on the hour, and the launch "
        "trigger SPEC §7.3 describes stops existing."
    )


def test_the_debounce_is_measured_per_section_rather_than_across_the_institution(
    roster_sync: Any,
    synced_section: Any,
    a_section_with_no_address: Any,
    committed_rows: Any,
    record_a_call: Any,
    enqueues: Any,
) -> None:
    """The window belongs to the section, not to the tool.

    **The mutation this kills**: a debounce that reads the most recent `nrps_call`
    row in the table rather than the most recent one *for this section*. With one
    section under test it is invisible — the only row there is is that section's —
    and in a live institution it would silence every launch trigger for five
    minutes after any section synced, which on an hourly schedule across a few
    hundred sections is every launch trigger there is.

    The second section is the one carrying no address, because that is the section
    a test has to hand: a stored address is not what the debounce reads, and using
    one here would not change the question.
    """
    other = a_section_with_no_address(synced_section)
    record_a_call(other, seconds_ago=A_SECOND)

    before = len(enqueues.calls)
    roster_sync.call(
        roster_sync.request_section_sync,
        session=committed_rows.session,
        section_id=synced_section.id,
    )

    assert len(enqueues.calls) == before + 1, (
        "A section with no call record of its own was debounced by a call made a second ago "
        "against a *different* section. The window D9 gives is 'the section has an `nrps_call` row "
        "younger than 5 minutes', and a query that forgot its `WHERE section_id = …` silences "
        "every launch trigger in the institution for five minutes after any section syncs."
    )


def test_a_section_with_no_stored_address_is_never_called_and_stays_distinct_from_a_synced_empty_one(
    roster_sync: Any,
    synced_section: Any,
    a_section_with_no_address: Any,
    service_wire: Any,
    compose_a_roster: Any,
    committed_rows: Any,
    roster_rows: Any,
    roster_contract: Any,
) -> None:
    """SPEC §7.3's never-synced state, asserted as a state rather than as a silence.

    "Never-synced remains visible: a section provisioned by a student launch (no
    address) is distinguishable from a synced-empty section in whatever record the
    job writes — E11's console reads it later; E1 asserts the state exists."

    The two sections in this test are the two states, side by side, and the record
    D9 gives is what tells them apart: the addressed section is synced against an
    **empty** roster, so it has call rows and no enrollments; the addressless one
    has no call rows at all. A console reading `nrps_call` can then say "never
    synced" of the second and "synced, nobody enrolled" of the first, which SPEC
    §7.3 insists are different states and only one of them a fault.

    **The mutation this kills**: a scheduled walk that takes every section rather
    than every section with a stored address. It would attempt a sync with no URL,
    which either raises per section — turning one unprovisionable section into a
    job that dies — or writes a failed call row, which makes the never-synced
    section look like a section whose platform is refusing the tool.

    **The near miss it must not fire on** is the addressed section beside it: a
    walk that took nothing at all would satisfy the "never called" half and the
    hourly job would do nothing.
    """
    never_synced = a_section_with_no_address(synced_section)
    service_wire.serve(compose_a_roster(synced_section, [], 5))

    roster_sync.call(
        roster_sync.sync_every_stored_address,
        session=committed_rows.session,
        http=service_wire.session(),
    )
    committed_rows.commit()

    synced_empty = roster_rows.calls_for(synced_section.id)
    assert synced_empty, (
        "The section carrying a stored roster address was not called at all, so the walk "
        "discovered nothing and the assertion below would hold for a job that does nothing. SPEC "
        "§7.3: the stored address 'is what gives the scheduled job the discovery it otherwise "
        "lacks'."
    )
    assert not roster_rows.enrollments(), (
        "The roster served was empty and enrollments exist, so this is not the synced-empty state "
        "this test is about."
    )
    assert not roster_rows.calls_for(never_synced), (
        f"The section with no stored roster address has `{roster_contract.nrps_call_table}` rows: "
        f"{[dict(row) for row in roster_rows.calls_for(never_synced)]}. Nothing can be attempted "
        "for it — there is no URL to call — so a row here is a call that never happened, and it "
        "makes SPEC §7.3's two states indistinguishable: 'a section with no roster and a section "
        "with no enrollments are different states and only one of them is a fault'."
    )
