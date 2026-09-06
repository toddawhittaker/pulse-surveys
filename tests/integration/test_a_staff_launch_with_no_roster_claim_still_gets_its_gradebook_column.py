"""A launch that advertises a gradebook and no roster — E3-08's boundary round, R6 / LO-M5.

R6's ruling: "The launch door's line-item trigger keys on the section the context
resolved to, independent of whether this launch carried a roster address. §7.3's
three limbs (instructor / leadership-in-purview / student never) are unchanged."

**This is the executed guard on that fix, and until it landed the fix had none.**
`docs/disputes/E3-08-03.md` established where the defect actually sat:
`request_line_item_creation` has keyed on `section.lms_ags_line_items_url` since
E3-05 and was never the problem, so
`test_the_line_item_trigger_does_not_depend_on_a_roster_address.py` — which drives
that trigger directly — is a standing control and could not have been red. The
conditioning was one level up, in `app.services.provisioning.provision_from_launch`,
which answered `None` for a staff launch that stored no roster address. **Both** of
the launch door's triggers ride on that answer, so a section provisioned by such a
launch got no roster sync and no gradebook column, and the sweep skipped it for the
life of the term because `ags_line_item_url` stayed NULL.

**Why the claim set is real rather than exotic.** LTI 1.3 makes each service claim
independent: a platform advertises AGS and NRPS separately and nothing in the
specification requires both. An administrator who enabled grade passback for this
tool and not roster access is a supported configuration, and it is exactly the
deployment that most wants the passback.

**Driven through the door, not around it.** The launch is minted by the platform
and delivered to the tool's own launch route, so what is asserted is what the door
does — not what a service does when a test hands it a claims mapping. That
distinction is
`test_the_leadership_limb_of_a_staff_launch.py`'s and it is kept here for the same
reason: a test that composed claims itself would say nothing about whether the door
calls the thing under test at all.

**The launch comes from `?defect=no_roster_service`**, the near-miss fixture E3-08
adds to `mock-lms/app/wrong_launches.py::NEAR_MISS_FIXTURES` in
`titleless_context`'s shape — the whole `namesroleservice` claim deleted, because
an absent key is what such a launch carries on the wire. A *near-miss fixture*
rather than a wrong launch: nothing about this token is malformed and the door must
accept it. The selector name is copied into
`tests/integration/test_mock_lms_wrong_launches.py`'s `ALL_SELECTORS`, which is
compared against the served `/mock/defects` list in both directions — so a rename
on either side fails there, by name, rather than as a 400 inside this module.

**Which failure a red here is.** Both tests are expected **green**: the R6 fix has
landed, and this is the guard it lacked rather than a case that drives it red to
green. A red in the first test is that fix reverted or narrowed. A red in the
second is that fix *widened* — which is the more likely wrong turn and is why the
second test exists.
"""

from typing import Any

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.lti]

# `gradebook_door`, `line_item_contract` and `a_closed_broker` come from
# `tests/fixtures/line_item_creation.py`; `provisioning_contract`, `launch_ground`
# and `provisioned_rows` from `tests/fixtures/provisioning.py`;
# `celery_application_in` from `tests/fixtures/repo.py`.

# The selector the platform mints this module's launches by. **This module's own
# literal**, matching the copy in `test_mock_lms_wrong_launches.py` rather than
# importing it: a test module that imports a sibling test module depends on where
# pytest put `tests/` on `sys.path`, and an import error is not a red. That copy is
# the one held against the served vocabulary in both directions, so a drift here
# shows up there first, naming both spellings.
NO_ROSTER_SERVICE = "no_roster_service"


def a_launch_at(door: Any, contract: Any, launch_ground: Any, offer: Any) -> Any:
    """Seed the containment rows this launch resolves against, and hand back its label.

    This module's own copy of the helper in
    `test_a_staff_launch_creates_the_participation_line_item.py`, for the reason
    that module gives about importing across test modules.
    """
    label = contract.label_of(door.driver.claims_of(offer))
    launch_ground(label)
    return label


def running_inline(
    monkeypatch: pytest.MonkeyPatch,
    celery_application_in: Any,
    line_item_contract: Any,
    door: Any,
) -> None:
    """Both substitutions, in the order the tests need them, with one call.

    Copied for the same reason, and **deliberately not a fixture** for the reason
    the original gives: both import `app.*` modules, which only resolve to the
    objects the door holds once the door has been built, and it is where the two
    deliverable guards fire — a guard in a fixture turns a module's reds into setup
    errors (`docs/MISTAKES.md` entry 44).
    """
    line_item_contract.run_tasks_inline(monkeypatch, celery_application_in)
    line_item_contract.reaching_the_platform(monkeypatch, door.wire)


def sections_coded(rows: Any, contract: Any, label: Any) -> list[Any]:
    """Every `section` row carrying the code this launch's label names."""
    return [row for row in rows.sections() if row.get(contract.section_code_column) == label.code]


def the_one_section(rows: Any, contract: Any, label: Any) -> Any:
    """The single section this launch bound, or a failure saying which way it went wrong."""
    found = sections_coded(rows, contract, label)
    assert len(found) == 1, (
        f"There are {len(found)} sections coded {label.code!r} after this launch: "
        f"{[dict(row) for row in found]}.\n\n"
        "**Zero is the defect this module exists for**: before E3-08's R6 fix, "
        "`provision_from_launch` answered `None` for a staff launch that stored no roster "
        "address, so a launch advertising AGS and not NRPS bound no section at all — and both of "
        "the door's triggers, the roster sync and the line item, ride on that answer. More than "
        "one is a writer that inserts on every launch, which is E1-10's rule rather than this "
        "ticket's."
    )
    return found[0]


def stored_on(section: Any, column: str, ticket_says: str) -> Any:
    """One column of a `section` row, or a failure naming the column that owes it.

    A `row[column]` on a mapping with no such key raises `KeyError` from inside the
    assertion, which reads as a broken test rather than as a missing deliverable.
    """
    if column not in section:
        pytest.fail(
            f"`section` carries no `{column}` column — it carries {sorted(section.keys())}. "
            f"{ticket_says}"
        )
    return section[column]


def line_item_id(item: Any) -> str:
    """One AGS line item's own address, which is its `id` member."""
    identifier = item.get("id")
    assert isinstance(identifier, str) and identifier, (
        f"The platform served the line item {item!r}, whose `id` is not an address. AGS 2.0 makes "
        "a line item's `id` its own URL, and that is the value E3-05 stores."
    )
    return identifier


def the_launch_carries_a_gradebook_and_no_roster(signed: Any, contract: Any) -> str:
    """Both halves of the premise, asserted before anything rests on them.

    **This is the control that the selector removed something, and removed only the
    right thing** (`docs/MISTAKES.md` entry 3). Without the first half, a selector
    that silently did nothing would leave every assertion in the first test below
    green for the ordinary reason — the launch would carry a roster address,
    `provision_from_launch` would answer a section id because it always did, and
    the guard would be measuring nothing. Without the second, a selector that
    removed the *AGS* claim as well would make the line-item assertions red for a
    reason that has nothing to do with R6.

    Answers the advertised container address, which the caller compares against
    what the section stored.
    """
    assert contract.nrps_claim not in signed.claims, (
        f"The launch minted with `?defect={NO_ROSTER_SERVICE}` still carries "
        f"`{contract.nrps_claim}`: {signed.claims.get(contract.nrps_claim)!r}. That selector exists "
        "to delete the claim whole — an absent key, not a key holding an empty object, which is "
        "what a platform advertising no roster service actually sends. With the claim present "
        "this is an ordinary launch and every assertion below passes for the ordinary reason."
    )
    return contract.line_items_url_in(signed.claims)


def test_a_staff_launch_advertising_a_gradebook_and_no_roster_is_provisioned_and_gets_its_column(
    gradebook_door: Any,
    provisioning_contract: Any,
    line_item_contract: Any,
    launch_ground: Any,
    provisioned_rows: Any,
    a_closed_broker: str,
    celery_application_in: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """R6 at the door: no roster claim, and the section is still provisioned and still scored.

    One instructor launch, at the real door, from a platform advertising its AGS
    endpoint and no `namesroleservice`. Afterwards the section exists, it carries
    the gradebook container address the launch advertised, its roster column is
    NULL, and the launched context's container holds exactly one Pulse
    Participation line item whose `id` the section stored.

    **The mutation this kills**: `provision_from_launch` reverting to answering no
    section id when no roster address is stored. That is the state before E3-08's
    R6 fix, and it is invisible to every other test in this epic because every
    launch the mock signs carries both service claims and every fixture section
    therefore holds both addresses. It is also invisible to
    `test_the_line_item_trigger_does_not_depend_on_a_roster_address.py`, which
    drives the trigger with a section id already in hand — the whole thing the
    defect withheld.

    **Four assertions, and they fail differently.** The section existing is the one
    the mutation moves; the NULL roster column is what says the case posed is the
    case intended; the stored gradebook address is what says provisioning ran
    *fully* rather than inserting a bare row; and the line item plus its stored id
    is what says the second trigger fired on the answer the first one produced.

    **The premise runs first** and is the whole instrument: the launch really does
    lack the roster claim and really does carry the AGS one.
    """
    door = gradebook_door(**{line_item_contract.redis_url_variable: a_closed_broker})
    offer = door.instructor_offer(provisioning_contract)
    label = a_launch_at(door, provisioning_contract, launch_ground, offer)
    running_inline(monkeypatch, celery_application_in, line_item_contract, door)

    response, signed = door.driver.launch(offer, defect=NO_ROSTER_SERVICE)

    advertised = the_launch_carries_a_gradebook_and_no_roster(signed, provisioning_contract)
    door.driver.accepted(response, "an instructor launch advertising AGS and no roster service")

    section = the_one_section(provisioned_rows, provisioning_contract, label)
    assert (
        stored_on(
            section,
            provisioning_contract.section_address_column,
            "E1-10 adds it for the roster address SPEC §7.3 has a staff launch store.",
        )
        is None
    ), (
        f"The section stored a roster address after a launch that advertised none: "
        f"{section.get(provisioning_contract.section_address_column)!r}. Nothing could have "
        "supplied it, so a value here means this launch was not the one this test minted — and "
        "the provisioning assertions around it are then about an ordinary two-claim launch."
    )
    assert (
        stored_on(
            section,
            provisioning_contract.section_ags_address_column,
            "E3-02 adds it for the AGS line-item container a launch advertises, and E1-10's "
            "provisioning writer stores it.",
        )
        == advertised
    ), (
        f"The section carries `{provisioning_contract.section_ags_address_column}` = "
        f"{section.get(provisioning_contract.section_ags_address_column)!r} and the launch "
        f"advertised {advertised!r}. R6's ruling is that the two addresses move independently: a "
        "launch missing the roster claim must still have its gradebook address stored, and a "
        "section provisioned without one has nowhere for a line item to be created."
    )
    created = door.pulse_items_in(signed)
    assert len(created) == 1, (
        f"The launched context's container holds {len(created)} line items carrying "
        f"{line_item_contract.resource_id!r} after an instructor's first launch with no roster "
        f"claim: {created}. SPEC §3.4 gives every section one Pulse Participation column on first "
        "launch, and §7.3's roster limb has nothing to do with it. Zero is R6's defect reaching "
        "the gradebook.\n\n"
        f"Everything the container holds: {door.items_in(signed)}."
    )
    assert stored_on(
        section,
        line_item_contract.line_item_column,
        "E3-02 adds it as a nullable text column for the id of the line item this tool creates, "
        "and E3-05's work order (D3) makes `ensure_line_item` its writer.",
    ) == line_item_id(created[0]), (
        f"The section carries `{line_item_contract.line_item_column}` = "
        f"{section.get(line_item_contract.line_item_column)!r} and the line item the platform "
        f"holds is {line_item_id(created[0])!r}. A line item created and not recorded is one the "
        "weekly sweep has to re-find by walking the container, and ADR 0052's retry identity has "
        "nothing to address."
    )


def test_a_student_launch_with_no_roster_claim_provisions_nothing_and_asks_for_nothing(
    gradebook_door: Any,
    provisioning_contract: Any,
    line_item_contract: Any,
    launch_ground: Any,
    provisioned_rows: Any,
    a_closed_broker: str,
    celery_application_in: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The other direction, and it guards the *over*-correction rather than the defect.

    The same launch, missing the same claim, by a student. SPEC §7.3's third limb —
    "student never" — is unchanged by R6, so this launch must bind no section and
    create no column.

    **The mutation this kills, and it is the more likely wrong turn.** R6's fix is
    "stop answering `None` when no roster address was stored", and the careless
    form of it is `provision_from_launch` answering a section id whenever it can
    resolve a context at all — the staff check dropped along with the roster
    condition. That widening passes the first test in this module perfectly, and it
    hands every student who launches a section a provisioning write and a gradebook
    column created in their name. Posed at the door over the *same* selector, so
    the only thing separating the two cases is the launcher's role.

    **Why this is the near miss and not the no-gradebook one.** The other refusing
    direction — a section with no container address must still be walked past — is
    held at trigger level by
    `test_the_line_item_trigger_does_not_depend_on_a_roster_address.py::test_a_section_with_no_gradebook_container_still_asks_for_nothing`,
    and it cannot be posed at the door today: no selector in the platform's
    vocabulary omits the AGS claim, so a launch carrying neither service claim is
    unmintable. E3-08 added one selector, not two. That boundary is stated rather
    than left to be discovered (`docs/MISTAKES.md` entry 14), and the two tests
    together cover both refusing directions at the two levels each can be reached
    at.

    **The premise runs first**, as above: without it a selector that quietly did
    nothing would make this test green for the ordinary reason that students never
    provision anyway.
    """
    door = gradebook_door(**{line_item_contract.redis_url_variable: a_closed_broker})
    offer = door.student_offer(provisioning_contract)
    label = a_launch_at(door, provisioning_contract, launch_ground, offer)
    running_inline(monkeypatch, celery_application_in, line_item_contract, door)

    response, signed = door.driver.launch(offer, defect=NO_ROSTER_SERVICE)

    the_launch_carries_a_gradebook_and_no_roster(signed, provisioning_contract)
    door.driver.accepted(response, "a student launch advertising AGS and no roster service")

    roles = signed.claims.get(provisioning_contract.roles_claim) or []
    assert provisioning_contract.instructor_role_urn not in roles, (
        f"The launch this test drove carries {roles!r}, which includes the Instructor URN — so it "
        "is a staff launch, and whatever it did says nothing about §7.3's student rule. The "
        "premise is asserted here rather than assumed because this test's whole instrument is that "
        "the launcher's role is the only difference from the case above."
    )
    bound = [dict(row) for row in sections_coded(provisioned_rows, provisioning_contract, label)]
    assert not bound, (
        f"A student's launch bound a section: {bound}. SPEC §7.3's third limb is 'student never', "
        "and R6 leaves all three limbs unchanged. This is the shape a fix for R6 takes when it "
        "removes the roster condition and the staff check together — and with a section bound, "
        "the trigger below has something to act on."
    )
    created = door.pulse_items_in(signed)
    assert not created, (
        f"A student's launch created {created} in the launched context's container. The column is "
        "created on a *staff* launch (SPEC §3.4, E3-05), and a student who opens their own survey "
        "is not who creates the gradebook column they are graded in.\n\n"
        f"Everything the container holds: {door.items_in(signed)}."
    )
    assert not door.wire.calls, (
        f"A student's launch made {[str(call) for call in door.wire.calls]} on the outbound "
        "transport. Nothing about a student launch may reach the platform's grade services at all, "
        "and a call that was made and refused is still a call this tool had no authorization to "
        "make. Read beside the empty container above: that says nothing was created, and this says "
        "nothing was attempted."
    )
