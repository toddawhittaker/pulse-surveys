"""What the launch trigger asks for, and what it declines to ask for — ticket E3-05.

The door's side of SPEC §3.4's "created by the tool on first launch" is one call:
`request_line_item_creation(session, section_id)`, on the answer
`provision_from_launch` already computed (work order decision D1 — "no second role
or purview check anywhere"). This module is about what that call does with the two
states of the section it is handed, and both of them are states the criteria name.

**Criterion 4 — a section whose platform advertised no container.**

> A section whose launch carried no AGS claim gets no creation attempt and the
> state E3-02 records, not an error.

`section.lms_ags_line_items_url` NULL is that state, and E3-02 already rules that
it is "a state to record and not a fault to raise". A platform that grants this
tool no gradebook scope sends no endpoint claim, which is an institution's
configuration; asking a worker to go and create a line item somewhere unknown is
work that can only fail, and recording a fault about it fills E11's surface with a
line for every section in such an institution.

**Criterion 1's second half and decision D5 — a section that already has one.**

> Retry on the next qualifying launch while `ags_line_item_url` is NULL; once an
> id is stored no launch enqueues anything.

That is the rule the ticket asks to be written down ("Retrying every launch and
retrying never are both wrong"), and it is what makes D3's deliberate absence of a
debounce affordable: the steady-state cost of a staff launch is one column read.

**Both tests are pairs on one section, and the pair is the point.** Each drives
the trigger against the same section twice, moving exactly one column between the
two calls, and requires opposite answers. A test that only asserted the refusing
half would be satisfied by a trigger that enqueues nothing at all — which is the
state at HEAD, where there is no trigger — and a test that only asserted the
enqueuing half would be satisfied by one that enqueues for every section in the
institution on every launch. Neither half is evidence without the other
(`docs/MISTAKES.md` entry 2, and entry 3's rule about a check satisfied by
emptiness).

**Driven at the service rather than through the door**, and deliberately: a launch
minted by the in-repo platform always carries an AGS claim, so criterion 4's
section cannot be produced by any launch this suite can drive — the same split
`test_a_launch_stores_the_gradebook_address_it_was_given.py` makes for the
addresses it refuses, borrowed whole rather than reinvented (`docs/MISTAKES.md`
entry 13). What the door does with the answer is asserted through the door, in
`test_a_staff_launch_creates_the_participation_line_item.py`.

**The enqueue is recorded rather than performed**, in both spellings, by the
recorder E1-11's debounce module used and this ticket shares
(`tests/fixtures/line_item_creation.py::Enqueues`). What a recorded enqueue proves
is an intention; that a line item actually appears is asserted against the
platform's own container in the door module. Both are needed and neither is the
other.

**Which failure a red is.** Before E3-05 lands, every test here is expected red on
`pytest.fail` naming `app.services.grading` as a module that does not exist, or
naming `create_line_item` as a task `app.jobs.tasks` does not define. Both guards
are plain calls in a test body, so the red is a FAILED and never an ERROR in setup
(`docs/MISTAKES.md` entry 44).
"""

from typing import Any

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.lti]

# `ags_sections` and `ags_contract` come from `tests/fixtures/ags_client.py`;
# `line_item_contract` and `creation_enqueues` from
# `tests/fixtures/line_item_creation.py`; `committed_rows` and `metadata_tables`
# from `tests/fixtures/authz_data.py` and `tests/fixtures/database.py`;
# `provisioned_rows` from `tests/fixtures/provisioning.py`. All are reached as
# fixtures rather than imported: an import of a fixtures module by name depends on
# where pytest put `tests/` on `sys.path`, and an import error is not a red.

# A line-item id nothing in this run creates, for the "already has one" half of the
# second pair. It is a plausible AGS line-item address on a host that resolves
# nowhere (RFC 2606's reserved suffix), because the trigger must decide on the
# column's *emptiness* and never on what the value points at — a trigger that
# dialled this to find out would be doing the worker's job on the request path.
AN_ALREADY_STORED_LINE_ITEM = "https://gradebook.pulse-e3-05.invalid/lineitems/1/lineitem"

# Why the deliverables this module names are owed, said once and passed to the
# guards so a red carries the record rather than a bare AttributeError.
TRIGGER_IS_OWED = (
    "E3-05's work order (D3) puts `request_line_item_creation(session, section_id) -> bool` "
    "there: it reads the Section, answers False without enqueueing when the container address is "
    "NULL (criterion 4) or when a line-item id is already stored (criterion 1's second half and "
    "D5's retry rule), and otherwise publishes the creation task through the bounded "
    "`publish_once`. It never raises and never blocks the launch."
)


def trigger(line_item_contract: Any) -> Any:
    """`request_line_item_creation`, or a failure naming the deliverable that owes it.

    Resolved in the test body rather than in a fixture, so a tree without the
    service produces a FAILED naming it instead of an ERROR in setup
    (`docs/MISTAKES.md` entry 44).
    """
    return line_item_contract.named_in(
        line_item_contract.grading(),
        line_item_contract.request_line_item_creation,
        TRIGGER_IS_OWED,
    )


def names_the_section(calls: list[Any], section_id: Any) -> bool:
    """Whether any recorded enqueue carries this section's identifier.

    Read out of the whole recorded call rather than out of a named argument,
    because D2 settles that `publish_once(task, *, args=…)` calls
    `task.apply_async(args=…)` and settles nothing about whether the id travels as
    a string or as a `UUID` — pinning either would settle an interface the work
    order leaves to the implementer. What it must not be is *some other section*,
    which is what this can see.
    """
    return any(str(section_id) in repr(call) for call in calls)


def test_a_section_with_a_container_address_is_asked_for_a_line_item_and_one_without_is_not(
    ags_sections: Any,
    line_item_contract: Any,
    creation_enqueues: Any,
    committed_rows: Any,
    metadata_tables: dict[str, Any],
) -> None:
    """Criterion 4, both directions, one column apart on one section.

    > A section whose launch carried no AGS claim gets no creation attempt.

    The accepted half runs first, and that ordering is the test's own control: it
    is what makes the refusal below a refusal rather than the silence of a trigger
    that does nothing at all (`docs/MISTAKES.md` entry 3 — where a test can be
    satisfied by emptiness, assert non-emptiness first). The section then has its
    container address set to NULL — E3-02's never-configured state, and the only
    thing that changes between the two calls — and the same trigger is asked
    again.

    **The enqueue is required to name this section**, not merely to have happened.
    A trigger that published a constant, or the last section it saw, would satisfy
    a count while every institution's gradebook column was created in one course.

    **The mutation this kills**: the container check dropped from
    `request_line_item_creation`, so a section whose platform grants no gradebook
    scope enqueues a task on every staff launch for the rest of the term — work
    that can only fail, once per launch, with nothing on §6.3's console explaining
    why. And, in the other direction, a check written as "enqueue only when *both*
    columns are set", which passes the refusing half and means no line item is
    ever created for any section, because `ags_line_item_url` is NULL until one
    is.
    """
    section = ags_sections()
    request = trigger(line_item_contract)
    enqueues = creation_enqueues()

    request(committed_rows.session, section.id)

    assert len(enqueues) == 1, (
        f"A section holding the container address its platform advertised "
        f"({section.container!r}) and no line-item id enqueued {len(enqueues)} creation tasks: "
        f"{enqueues.calls}. SPEC §3.4 gives that section one line item, created by the tool, and "
        "this is the only thing that asks for it — with nothing enqueued no gradebook column ever "
        "appears, and the refusal below would be the silence of a trigger that never fires."
    )
    assert names_the_section(enqueues.calls, section.id), (
        f"The enqueued task does not carry this section's id {section.id!r} anywhere: "
        f"{enqueues.calls}. A creation task that names some other section creates a participation "
        "column in a course nobody launched, and counts alone cannot tell the two apart."
    )

    line_item_contract.set_section_values(
        committed_rows,
        metadata_tables,
        section.id,
        **{line_item_contract.container_column: None},
    )
    before = len(enqueues)

    request(committed_rows.session, section.id)

    assert len(enqueues) == before, (
        f"A section whose `{line_item_contract.container_column}` is NULL enqueued a creation "
        f"task: {enqueues.calls[before:]}. That column is E3-02's never-configured state — 'a "
        "platform that supplies no AGS claim is a section with no gradebook, which is a state to "
        "record and not a fault to raise' — so there is no container to create a line item in and "
        "nothing a worker could do but fail."
    )


def test_a_section_with_no_container_address_raises_nothing_and_records_no_defect(
    ags_sections: Any,
    line_item_contract: Any,
    creation_enqueues: Any,
    committed_rows: Any,
    provisioned_rows: Any,
    metadata_tables: dict[str, Any],
) -> None:
    """Criterion 4's second clause: "the state E3-02 records, not an error".

    Three things a section with no gradebook must **not** produce, and they fail
    differently. A raise, because this call sits on the launch path after the
    launch has already done its own job and a person is waiting on the response —
    D3: "never raises, never blocks the launch". A defect row, because §6.3's
    console is a list of things a human is asked to act on and there is nothing to
    do about a platform that grants no gradebook scope; E3-02 settled exactly this
    for the address and this ticket must not undo it one service over. And a
    written column, because the only honest value for a line item nobody could
    create is the NULL that is already there.

    **The mutation this kills**: a trigger that treats the absent container as the
    refused one — the same conflation E3-02's absent-claim test exists for, arriving
    a ticket later on the enqueue side rather than on the write side.

    **Its pair is the test above**, which is what says the trigger fires at all;
    this one would otherwise be satisfied by a service that does nothing whatever.
    """
    section = ags_sections(container=False)
    request = trigger(line_item_contract)
    creation_enqueues()

    answered = request(committed_rows.session, section.id)

    assert answered is not True, (
        f"The trigger answered {answered!r} for a section with no gradebook address. D3 makes the "
        "answer True only for a publish that went out, and a truthful answer here is what a "
        "later caller — and §6.3's console — reads as 'a line item was asked for'."
    )
    recorded = [dict(row) for row in provisioned_rows.defects()]
    assert not recorded, (
        f"A section with no gradebook address left {recorded} in the launch-defect table. E3-02 "
        "ruled the absent claim a state rather than a fault, and a row per such section makes "
        "E11's surface a list of every course whose institution never granted the scope."
    )
    row = line_item_contract.section_row(committed_rows, metadata_tables, section.id)
    assert row.get(line_item_contract.line_item_column) is None, (
        f"The section carries `{line_item_contract.line_item_column}` = "
        f"{row.get(line_item_contract.line_item_column)!r} after a trigger that had no container "
        "to create anything in. Nothing was created, so a value here was composed rather than "
        "read, and E3-06 would post a score to whatever the composition guessed."
    )


def test_a_section_that_has_no_line_item_id_is_asked_again_and_one_that_has_is_not(
    ags_sections: Any,
    line_item_contract: Any,
    creation_enqueues: Any,
    committed_rows: Any,
) -> None:
    """Decision D5's retry rule, both directions, one column apart on one section.

    > Retry on the next qualifying launch while `ags_line_item_url` is NULL; once
    > an id is stored no launch enqueues anything.

    This is what makes criterion 1's "a second launch creates nothing further" a
    property of the trigger rather than a property of the mock's reconciliation,
    and it is what pays for D3's deliberate absence of a debounce: a section in
    the steady state costs one column read per staff launch and no task at all.

    **The retrying half runs first**, so the refusal below is a refusal rather
    than a trigger that never fires — the same ordering argument as the pair
    above.

    **The stored id is one nothing in this run created**, on a host that resolves
    nowhere. That is deliberate: the rule is about the column being *set*, and a
    trigger that dialled the stored address to check it was still there would be
    doing the worker's job on a request path — which is precisely what
    `docs/MISTAKES.md` entry 41 is about, and it would go red here rather than
    quietly costing every launch a round trip.

    **The mutation this kills**: the stored-id check dropped, so every staff
    launch of every section in the institution publishes a creation task for the
    rest of the term. Against a platform that reconciles by `resourceId` no
    gradebook changes, so nothing about the container would notice — this is the
    only assertion in the ticket that would.

    **And the mutation on the other side**: "enqueue only when the id is stored",
    which is the same condition written backwards. It passes nothing here, and
    without the retrying half it would pass the whole ticket while no section ever
    got its first line item.
    """
    section = ags_sections()
    request = trigger(line_item_contract)
    enqueues = creation_enqueues()

    request(committed_rows.session, section.id)

    assert len(enqueues) == 1, (
        f"A section with no `{line_item_contract.line_item_column}` enqueued {len(enqueues)} "
        f"creation tasks: {enqueues.calls}. D5's rule is to retry 'on the next qualifying launch "
        "while `ags_line_item_url` is NULL', and a section whose first creation failed would "
        "otherwise never be asked again — no scheduled backstop exists in this ticket, by "
        "decision, so this call is the only retry there is."
    )

    ags_sections.store_line_item(section, AN_ALREADY_STORED_LINE_ITEM)
    before = len(enqueues)

    request(committed_rows.session, section.id)

    assert len(enqueues) == before, (
        f"A section already carrying `{line_item_contract.line_item_column}` = "
        f"{AN_ALREADY_STORED_LINE_ITEM!r} enqueued another creation task: "
        f"{enqueues.calls[before:]}. SPEC §3.4 gives a section one line item and this tool has "
        "already recorded which one it is; a task per launch is a class of thirty students' worth "
        "of work every hour, asking a platform to create a column that exists."
    )
