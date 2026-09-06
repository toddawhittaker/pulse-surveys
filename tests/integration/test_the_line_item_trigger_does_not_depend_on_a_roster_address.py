"""The line-item trigger keys on the section, not on whether a roster address arrived — E3-08's boundary round, LO-M5.

R6's ruling: "The launch door's line-item trigger keys on the section the context
resolved to, independent of whether this launch carried a roster address. §7.3's
three limbs (instructor / leadership-in-purview / student never) are unchanged."

**What the defect is.** SPEC §7.3 has a staff launch store the section's roster
service address, and SPEC §3.4 has the tool create one AGS line item per section
on first launch. Those are two claims and two jobs, and the finding is that the
second was nested inside the first: the trigger sat on the branch that runs when a
roster address is present, so a launch carrying the AGS endpoint claim and **no**
`namesroleservice` claim provisioned the section and asked for no gradebook
column.

**Why that claim set is real rather than exotic.** LTI 1.3 makes each service
claim independent — a platform advertises AGS and NRPS separately, and there is
nothing in the specification requiring both. A platform whose administrator
enabled grade passback for a tool and not roster access is a supported
configuration, and it is exactly the deployment that most wants the passback. It
gets a section with no column, no error, and a weekly sweep that skips it forever
because `ags_line_item_url` is NULL.

**What this module drives, and what it deliberately does not.** It drives the
*trigger* — `request_line_item_creation(session, section_id)` — over a section
that carries a gradebook container address and **no** roster address, which is the
state such a launch leaves behind and is the exact premise the finding names: the
trigger's decision must be keyed on the section it was given, and on the container
that section holds, and on nothing about the roster.

It does **not** drive a signed launch whose `id_token` omits the
`namesroleservice` claim, and that boundary is stated rather than left to be
discovered (`docs/MISTAKES.md` entry 14). No such launch can be minted in this
suite today: `MockPlatform.mint` takes a `state`, a `nonce` and one of E1-07's
defect selectors, and none of those removes a service claim; the mock always signs
both. Producing one needs either a claim-omission selector on the mock — which is
the implementer's partition and which this round's brief holds untouched — or a
claims-override on the launch driver. Until one exists, what is asserted here is
the half of the ruling a test can reach, and the door's own call site stays
covered by review. **The half asserted is the half the defect lives in**: the
finding is that the trigger was conditioned on the roster address, and a trigger
that is not conditioned on it cannot be re-conditioned on it by a call site.

**Both directions, because the near miss is the whole risk.** A section with no
*container* address must still be walked past — E3-05 already refuses to enqueue
for one, and a fix for this finding that widened the trigger to "always enqueue"
would break that and would ask the worker to create a line item in a gradebook
whose address nobody has. So the roster address is varied while the container is
held, and then the container is taken away while the roster address is held.

**Which failure a red here is.** Expected **RED** on the first test before the
fix: no creation is requested for a section that carries no roster address. The
second is expected **green** both before and after, and is the control that says
the trigger still refuses what it should.
"""

from typing import Any

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.lti]

# `ags_sections` and `ags_contract` come from `tests/fixtures/ags_client.py`;
# `line_item_contract` from `tests/fixtures/line_item_creation.py`;
# `committed_rows` from the shared fixtures. All are reached as fixtures rather
# than imported, for the reason every module in this suite gives.

# The column SPEC §7.3's roster address is stored in, and the one §3.4's gradebook
# container arrives in. Spelled as `tests/fixtures/roster_sync.py` and
# `tests/fixtures/ags_client.py` spell them, so the two halves of this test read
# against the same names the rest of the suite does.
SECTION_ROSTER_COLUMN = "lms_nrps_context_memberships_url"


def rewrite(rows: Any, tables: dict[str, Any], section_id: Any, **values: Any) -> None:
    """Set columns on one `section` row and commit, so the trigger's own read sees them.

    `tests/fixtures/ags_client.py::rewrite_section`'s shape. Committed because the
    trigger reads the row on the session it is handed and a test that left the
    change in its own transaction would be asking about a section nobody wrote.
    """
    from fixtures.supervision import require_table, single_primary_key

    table = require_table(tables, "section")
    missing = [column for column in values if column not in table.c]
    assert not missing, (
        f"`section` declares no {missing} (it declares "
        f"{[column.name for column in table.columns]}). SPEC §7.3 stores the roster service "
        "address on the section and E3-02 adds the two gradebook columns beside it; without them "
        "this module cannot put a section into the state a launch with one claim and not the other "
        "leaves behind."
    )
    key = single_primary_key(table)
    rows.session.execute(table.update().where(table.c[key] == section_id).values(**values))
    rows.commit()


def creation_requested_for(
    line_item_contract: Any, rows: Any, section_id: Any
) -> tuple[Any, BaseException | None]:
    """Call E3-05's trigger for one section, answering what it returned and what escaped it.

    The exception is caught rather than allowed to fly for the reason E1-10's work
    order gives about every writer on the launch path: a provisioning refusal
    "NEVER fails the launch or the person's landing", so an exception reaching this
    far is a real outcome to report and is not the subject — and reporting it as
    the subject would hide which of the two actually failed.
    """
    trigger = line_item_contract.named_in(
        line_item_contract.grading(),
        line_item_contract.request_line_item_creation,
        "E3-05's work order (D3) puts the launch door's trigger there: "
        "`request_line_item_creation(session, section_id)`, which enqueues nothing for a section "
        "with no container address or with a line-item id already stored.",
    )
    try:
        return trigger(rows.session, section_id), None
    except Exception as escaped:
        return None, escaped


def test_a_section_with_a_gradebook_and_no_roster_address_still_asks_for_a_line_item(
    ags_sections: Any,
    line_item_contract: Any,
    committed_rows: Any,
    metadata_tables: dict[str, Any],
    ags_contract: Any,
) -> None:
    """LO-M5: the trigger reads the container, and never the roster address.

    A section carrying the gradebook container address and no roster address —
    the state a launch from a platform that advertises AGS and not NRPS leaves
    behind — must still have a line item requested for it.

    **The mutation this kills:** the trigger nested inside the branch that runs
    when a roster address is present, which is the state LO-M5 found. It is
    invisible to every other test in this epic, because every launch the mock signs
    carries both claims and every section in every other fixture therefore holds
    both addresses. The deployment it breaks is the one that most wants the
    passback: grade passback enabled, roster access not, a section with no column,
    no error anywhere, and a weekly sweep that skips it for the life of the term
    because `ags_line_item_url` stays NULL.

    **The two addresses are moved independently**, which is the whole instrument.
    The section keeps its container and loses its roster address, so the only thing
    that changed is the value the defect reads — a test that cleared both would be
    posing the control below instead.

    **Non-vacuity, and it is the load-bearing guard.** The section is required to
    hold a container address *after* the rewrite, because "the trigger asked for a
    line item" is a claim about a section it could act on at all: with the
    container gone too, the correct answer is to enqueue nothing and this test
    would be red against a correct implementation.
    """
    section = ags_sections()
    rewrite(
        committed_rows,
        metadata_tables,
        section.id,
        **{SECTION_ROSTER_COLUMN: None},
    )

    from fixtures.supervision import require_table, single_primary_key

    table = require_table(metadata_tables, "section")
    key = single_primary_key(table)
    row = dict(
        next(
            iter(
                committed_rows.session.execute(
                    table.select().where(table.c[key] == section.id)
                ).mappings()
            )
        )
    )
    assert row.get(ags_contract.container_column), (
        f"The section holds `{ags_contract.container_column}` "
        f"{row.get(ags_contract.container_column)!r} after this test cleared its roster address. "
        "The container is what a line item would be created *in*, so with it gone the correct "
        "answer is to enqueue nothing and this test would be red against a correct trigger — the "
        "control below is the case that is about."
    )
    assert row.get(SECTION_ROSTER_COLUMN) is None, (
        f"The section still holds `{SECTION_ROSTER_COLUMN}` {row.get(SECTION_ROSTER_COLUMN)!r}, so "
        "it is not in the state a launch carrying only the AGS claim leaves behind and the "
        "assertion below would pass whatever the trigger keys on."
    )

    answered, raised = creation_requested_for(line_item_contract, committed_rows, section.id)
    assert raised is None, (
        f"The trigger raised {raised!r} for a section with no roster address. E1-10's rule is that "
        "nothing on the launch path fails a person's landing, so a launch from a platform that "
        "advertises AGS and not NRPS must land its instructor whatever the trigger decides."
    )
    assert answered, (
        "The trigger requested no line-item creation for a section that holds a gradebook "
        f"container ({row.get(ags_contract.container_column)!r}) and no roster address.\n\n"
        "E3-08's boundary round (LO-M5): the trigger keys on the section the context resolved to, "
        "independent of whether this launch carried a roster address. LTI 1.3 makes the two "
        "service claims independent — a platform administrator can enable grade passback without "
        "roster access, and that is a supported configuration — so a trigger nested inside the "
        "roster-address branch leaves exactly that deployment with a section that has no gradebook "
        "column, no error, and a weekly sweep that skips it forever."
    )


def test_a_section_with_no_gradebook_container_still_asks_for_nothing(
    ags_sections: Any,
    line_item_contract: Any,
    committed_rows: Any,
    metadata_tables: dict[str, Any],
    ags_contract: Any,
) -> None:
    """The control: widening the trigger to "always enqueue" is the wrong fix.

    E3-05's own rule is that nothing is enqueued for a section with no container
    address — there is no gradebook to create a column in, and a worker asked to
    do it would fail on every run for the life of the section.

    **The mutation this kills:** the fix for the test above written as removing the
    condition altogether rather than as replacing the wrong one. That passes the
    test above perfectly and breaks the rule this one holds, which is the shape a
    hurried fix takes when a test says "it must enqueue here" and nothing says
    "and not there".

    **Green before this round and after it.** It is here because the pair is what
    makes the first test safe to satisfy, not because anything about it is
    expected to change.
    """
    section = ags_sections(container=False)
    answered, raised = creation_requested_for(line_item_contract, committed_rows, section.id)

    assert raised is None, (
        f"The trigger raised {raised!r} for a section with no gradebook container address. A "
        "launch from a platform advertising no AGS endpoint is an ordinary launch, and E1-10's "
        "rule is that nothing on this path fails a person's landing."
    )
    assert not answered, (
        f"The trigger requested a line-item creation ({answered!r}) for a section holding no "
        f"`{ags_contract.container_column}` at all. There is no gradebook to create a column in, "
        "so the worker would fail on every attempt for the life of the section.\n\n"
        "If the test above is green and this one is red, the fix for LO-M5 removed the condition "
        "rather than correcting it: the trigger must key on the *container*, which is what a line "
        "item is created in, and not on the roster address, which has nothing to do with it."
    )
