"""The line-item trigger keys on the section, not on whether a roster address arrived — E3-08's boundary round, LO-M5.

R6's ruling: "The launch door's line-item trigger keys on the section the context
resolved to, independent of whether this launch carried a roster address. §7.3's
three limbs (instructor / leadership-in-purview / student never) are unchanged."

**What the defect is, corrected by `docs/disputes/E3-08-03.md`.** SPEC §7.3 has a
staff launch store the section's roster service address, and SPEC §3.4 has the
tool create one AGS line item per section on first launch. Those are two claims
and two jobs, and the finding is that the second was made conditional on the
first: a launch carrying the AGS endpoint claim and **no** `namesroleservice`
claim asked for no gradebook column.

**Where the conditioning actually sat is one level above what this module
drives**, and this paragraph used to say otherwise. It read that "the trigger sat
on the branch that runs when a roster address is present". It did not:
`request_line_item_creation` has keyed on `section.lms_ags_line_items_url` since
E3-05. The conditioning was in `app.services.provisioning.provision_from_launch`,
which answered `None` — no section id at all — for a staff launch that stored no
roster address, and **both** of the launch door's triggers ride on that answer.
That is what the round's fix changed, and it is why this module is a control
rather than a red-to-green case.

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
discovered (`docs/MISTAKES.md` entry 14). **That case is now covered, one module
over**, and this paragraph used to say it could not be written at all.

The launch is minted by `?defect=no_roster_service`, the near-miss fixture E3-08
adds to `mock-lms/app/wrong_launches.py::NEAR_MISS_FIXTURES` in
`titleless_context`'s shape, and it is driven through the tool's own door in
`tests/integration/test_a_staff_launch_with_no_roster_claim_still_gets_its_gradebook_column.py`.
That module is the executed guard on R6's fix in `provision_from_launch`, which is
the thing this one cannot reach; it asserts the section is provisioned, stores its
gradebook address, and gets its line item, and its second test guards the
over-correction — a student launch through the same selector must still provision
and create nothing.

**What stays here rather than moving.** The refusing direction below — a section
with no *container* address is walked past — is a property of this trigger and
cannot be posed at the door: no selector omits the AGS claim, so a launch carrying
neither service claim is unmintable, and E3-08 added one selector rather than two.
The two modules together cover both refusing directions, each at the level it can
be reached at.

**What that costs, stated rather than implied, and it is more than this module
first claimed.** This paragraph used to end "the half asserted is the half the
defect lives in". It is not: the defect lived in `provision_from_launch`, one
level up, so what is proved here is the *standing* property — that the trigger
itself is keyed on the section and its container and on nothing about the roster —
and not the fix. Nothing in this module could have been red before the fix, and
nothing in it would go red if `provision_from_launch` were reverted. **The test
that would is now written**, in the module named above, and this sentence used to
say it was not — R6's fix went from asserted-by-review-alone to having an executed
guard inside the same round. What this module is remains what it always was: the
standing property, which is worth keeping precisely because a trigger that is not
conditioned on the roster address cannot be re-conditioned on it by a call site.

**Both directions, because the near miss is the whole risk.** A section with no
*container* address must still be walked past — E3-05 already refuses to enqueue
for one, and a fix for this finding that widened the trigger to "always enqueue"
would break that and would ask the worker to create a line item in a gradebook
whose address nobody has. So the roster address is varied while the container is
held, and then the container is taken away while the roster address is held.

**What is observed is the enqueue, and never the trigger's returned boolean**
(`docs/disputes/E3-08-04.md`). Both tests used to assert that return value, and it
cannot answer the question they ask. `request_line_item_creation` publishes inside
a `try` and answers `False` on **any** exception — `docs/MISTAKES.md` entry 41 and
ADR 0135, which make a request path unable to fail because a background dependency
was unavailable, and make the next qualifying launch the retry. So `False` means
"refused" *or* "the broker was unreachable", and this suite guarantees the second:
`documented_environment_baseline` lays `.env.example`'s `REDIS_URL` — the Compose
service name `redis` — into every test's environment, and no host-side process
resolves it. The publish always fails here.

**That made one test red for the environment and the other green for the wrong
reason**, and the second is the worse half. The container control expects `False`,
and `False` is what a failed publish answers whatever the container check does —
so deleting the container condition from the trigger left it green. As written,
this module asserted its rule in *neither* direction: `docs/MISTAKES.md` entry 3,
arriving through the environment rather than through a fixture. Both halves now go
through `creation_enqueues`, the interception
`test_the_line_item_trigger_asks_only_for_the_sections_that_need_one.py` already
uses, which records the enqueue instead of performing it — the observable that
survives the fail-open publish. The returned boolean is deliberately read and not
asserted; the helper below says so, so that nobody reinstates it.

**Which failure a red here is.** Both tests are expected **green**, before and
after — the first as the standing property above, the second as the near-miss
control that says the trigger still refuses a section with no container. The
prediction here has been wrong twice and both corrections are recorded rather than
quietly applied: it once read RED on the first test, when the module could not run
at all (`SECTION_ROSTER_COLUMN` named a column the schema does not declare, so
`rewrite`'s guard refused the argument at the first statement) and when the trigger
it drives was never where the defect was — `docs/disputes/E3-08-03.md`; and the
greens it then claimed rested on the boolean above — `docs/disputes/E3-08-04.md`.

The mutations these two kill are unchanged by either correction: the trigger
re-conditioned on the roster address, and the trigger widened to enqueue for a
section with no container.
"""

from typing import Any

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.lti]

# `ags_sections` and `ags_contract` come from `tests/fixtures/ags_client.py`;
# `line_item_contract` and `creation_enqueues` from
# `tests/fixtures/line_item_creation.py`; `committed_rows` from the shared
# fixtures. All are reached as fixtures rather than imported, for the reason every
# module in this suite gives.

# The column SPEC §7.3's roster address is stored in, and the one §3.4's gradebook
# container arrives in. Spelled as `tests/fixtures/roster_sync.py` and
# `tests/fixtures/ags_client.py` spell them, so the two halves of this test read
# against the same names the rest of the suite does.
#
# **It was `lms_nrps_context_memberships_url` and the schema declares no such
# column** (`docs/disputes/E3-08-03.md`). The comment above was true of where the
# value was meant to come from and false of the value: `roster_sync.py`'s
# `SECTION_ADDRESS_COLUMN`, `provisioning.py`'s of the same name, and E1-10's work
# order all spell it without the `nrps_`. The wrong string made `rewrite`'s own
# guard refuse the argument, so this module failed at its first statement — before
# the trigger was called at all — and could not have gone green against any
# implementation.
SECTION_ROSTER_COLUMN = "lms_context_memberships_url"


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
    the subject would hide which of the two actually failed. That half is still
    asserted by both tests below.

    **The returned value is handed back and neither test asserts on it. Do not
    reinstate that** (`docs/disputes/E3-08-04.md`). `request_line_item_creation`
    answers `False` on any exception out of its publish — `docs/MISTAKES.md`
    entry 41's fail-open contract — so the value cannot tell "the trigger refused"
    from "the broker was unreachable", and in this suite the broker is always
    unreachable: the autouse `documented_environment_baseline` points `REDIS_URL`
    at the Compose service name. Asserting it made one test red for the environment
    and left the other green with its condition deleted. The enqueue is the
    observable; this is kept only so a caller can print the value in a message.
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


def names_the_section(calls: list[Any], section_id: Any) -> bool:
    """Whether any recorded enqueue carries this section's identifier.

    A copy of the helper in
    `test_the_line_item_trigger_asks_only_for_the_sections_that_need_one.py`
    rather than an import of it — a test module that imports a sibling test module
    depends on where pytest put `tests/` on `sys.path`, and an import error is not
    a red — and it keeps that helper's reasoning: the id is read out of the whole
    recorded call rather than out of a named argument, because D2 settles that
    `publish_once(task, *, args=…)` calls `task.apply_async(args=…)` and settles
    nothing about whether the id travels as a string or as a `UUID`. Pinning either
    would settle an interface the work order leaves open. What it must not be is
    *some other section*, which is what this can see.
    """
    return any(str(section_id) in repr(call) for call in calls)


def test_a_section_with_a_gradebook_and_no_roster_address_still_asks_for_a_line_item(
    ags_sections: Any,
    line_item_contract: Any,
    creation_enqueues: Any,
    committed_rows: Any,
    metadata_tables: dict[str, Any],
    ags_contract: Any,
) -> None:
    """LO-M5: the trigger reads the container, and never the roster address.

    A section carrying the gradebook container address and no roster address —
    the state a launch from a platform that advertises AGS and not NRPS leaves
    behind — must still have a line item requested for it.

    **The mutation this kills:** the trigger nested inside the branch that runs
    when a roster address is present. That is **not** the state LO-M5 found —
    the conditioning was one level up, in `provision_from_launch`
    (`docs/disputes/E3-08-03.md`), so this test was green from the day the trigger
    was written and is a control rather than a red-to-green case. It is
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

    **The enqueue is the observable, not the trigger's return value**
    (`docs/disputes/E3-08-04.md`). This test used to assert that boolean and was red
    for the environment: the publish it reports on cannot succeed in a host-side
    process, because the documented `REDIS_URL` names a Compose service. The
    interception records the enqueue instead of performing it, so what is asserted
    is that the trigger *asked* — which is the decision under test — and the ask is
    required to name **this** section rather than merely to have happened, since a
    trigger publishing a constant would satisfy a count while every institution's
    column was created in one course.
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

    enqueues = creation_enqueues()
    _answered, raised = creation_requested_for(line_item_contract, committed_rows, section.id)

    assert raised is None, (
        f"The trigger raised {raised!r} for a section with no roster address. E1-10's rule is that "
        "nothing on the launch path fails a person's landing, so a launch from a platform that "
        "advertises AGS and not NRPS must land its instructor whatever the trigger decides."
    )
    assert len(enqueues) == 1, (
        f"The trigger enqueued {len(enqueues)} creation tasks for a section that holds a gradebook "
        f"container ({row.get(ags_contract.container_column)!r}) and no roster address: "
        f"{enqueues.calls}.\n\n"
        "E3-08's boundary round (LO-M5): the trigger keys on the section the context resolved to, "
        "independent of whether this launch carried a roster address. LTI 1.3 makes the two "
        "service claims independent — a platform administrator can enable grade passback without "
        "roster access, and that is a supported configuration — so a trigger nested inside the "
        "roster-address branch leaves exactly that deployment with a section that has no gradebook "
        "column, no error, and a weekly sweep that skips it forever."
    )
    assert names_the_section(enqueues.calls, section.id), (
        f"The trigger enqueued {enqueues.calls}, none of which names section {section.id}. A "
        "trigger that published a constant, or the last section it happened to see, would satisfy "
        "the count above while every institution's gradebook column was created in one course."
    )


def test_a_section_with_no_gradebook_container_still_asks_for_nothing(
    ags_sections: Any,
    line_item_contract: Any,
    creation_enqueues: Any,
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

    **It was green for the wrong reason until `docs/disputes/E3-08-04.md`, and that
    is the sharper half of that objection.** It asserted the trigger's returned
    boolean was falsey, and a failed publish answers `False` whatever the container
    check does — so in a suite whose broker is unreachable by construction, this
    control stayed green with the container condition **deleted**. It certified
    nothing, and it was the half meant to keep the test above honest
    (`docs/MISTAKES.md` entry 3, reached through the environment rather than
    through a fixture). Asserting the recorded enqueue is what makes its green mean
    something: an interception that records instead of publishing cannot be
    satisfied by a broker that was never there.
    """
    section = ags_sections(container=False)
    enqueues = creation_enqueues()

    _answered, raised = creation_requested_for(line_item_contract, committed_rows, section.id)

    assert raised is None, (
        f"The trigger raised {raised!r} for a section with no gradebook container address. A "
        "launch from a platform advertising no AGS endpoint is an ordinary launch, and E1-10's "
        "rule is that nothing on this path fails a person's landing."
    )
    assert len(enqueues) == 0, (
        f"The trigger enqueued {enqueues.calls} for a section holding no "
        f"`{ags_contract.container_column}` at all. There is no gradebook to create a column in, "
        "so the worker would fail on every attempt for the life of the section.\n\n"
        "If the test above is green and this one is red, the fix for LO-M5 removed the condition "
        "rather than correcting it: the trigger must key on the *container*, which is what a line "
        "item is created in, and not on the roster address, which has nothing to do with it."
    )
