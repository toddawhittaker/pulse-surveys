"""The launch that triggers a sync because of who launched — E1-12, criterion 6.

SPEC §7.3: "A launch by an instructor **or any leadership role** triggers a roster
sync; a **student** launch does not. The roster service address arrives as a claim
on that launch and is **stored**, which is what gives the scheduled job the
discovery it otherwise lacks." E1-10 built the instructor half and left the
leadership half stated and dormant, because resolving a launching subject to a live
`role_assignment` needs the `sub` → `user` → `person` link only this ticket builds
(ADR 0091: "until then a dean's launch discovers nothing… E1-12 carries the
accept-side criterion"). This module is that criterion.

**The distinguishing fact is the assignment, and the two tests differ by exactly
it.** Both drive the same launch — the same platform, the same context, the same
roles claim, a claim carrying no Instructor URN — by a subject linked to a `person`
row. In the first that person holds a live leadership assignment and the roster
address is stored. In the second they hold a Care assignment instead, and nothing
is written. One row apart, opposite answers: that is what makes the first evidence
about §7.3's leadership limb rather than evidence that a launch provisions
(`docs/MISTAKES.md` entry 3), and what stops "any linked person triggers a sync"
and "any assignment triggers a sync" from passing.

**Driven through the door, not around it.** The writer runs inside the launch
request and reads the claims that call verified; a test that handed it a claims
dict would say nothing about whether the door calls it at all.

**Nothing about the mock's seed is transcribed.** The context label, the course
number, the section code and the roster address are read off the launch the
platform signed, and the prefix, term and start-letter map rows those need are
seeded from those values by `launch_ground`.

**Deliberately not asserted: a sync being enqueued.** §7.3's "triggers the sync"
means the address that makes a sync possible is stored; E1-11 builds the client and
the schedule, and this ticket's boundary says to assert the address rather than a
queue.

**The environment** (`docs/MISTAKES.md` entry 40): `launch_driver` builds the door
through `tool_doors` over `configured_env`, so `ENVIRONMENT` is the development
name — which is what E1-10's address rules require before the mock's own cleartext
roster address is storable at all — and `DATABASE_URL` names the session-wide
testcontainers Postgres. Every row is removed by `committed_rows`'s diff-delete.

**E1-13 changes what the second test's launch is answered with, and the assertion
moved with it** (`docs/MISTAKES.md` entry 22). From that ticket the landing comes
from the launching person's own live assignments filtered by ADR 0026's
`permits_launch` — and a `CARE` assignment does not permit a launch, which is the
whole of §2.1's door rule. So the Care officer's launch is met with the calm
no-access page: not a refusal, and not a role route. That is *correct*, and it is
also this module's near miss working exactly as designed — the assignment that
authorizes nothing about a roster is the same assignment that opens no door here.
Her launch, and the instructor launch that follows it, therefore assert
`LaunchDriver.accepted`: the door did not refuse, so what the writer did or did
not store is attributable to the role that launched. The first test's dean is
unchanged and still asserts `landed`, because §2.1's table gives every leadership
role the LTI launch and her assignment really does open it.

**Giving her something to land on is deliberately not done.** An instructor
assignment would make her a different person and would invert the very rule this
module exists to hold; an enrollment would need a second `user` row for a subject
`a_linked_person` has already written one for, which ADR 0045's uniqueness
refuses. The difference between the two tests stays one row, and it stays the
assignment's role.
"""

from typing import Any

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.lti]

# `launch_driver`, `launch_ground`, `provisioning_contract` and `provisioned_rows`
# come from `tests/fixtures/provisioning.py`; `web_identity` from
# `tests/fixtures/web_identity.py`. Reached as fixtures rather than imported: an
# import of a fixtures module by name depends on where pytest put `tests/` on
# `sys.path`, and an import error is not a red.

# The two roles this module hangs on a linked person. `DEAN` is one of §2.1's
# supervision chain and is what §7.3's "any leadership role" is about; `CARE` sits
# outside the graph entirely (§2.1) and is the near miss — a live assignment,
# legitimately held, that authorizes nothing about a roster.
LEADERSHIP_ROLE = "DEAN"
NON_LEADERSHIP_ROLE = "CARE"

SUBJECT_CLAIM = "sub"


def sections_coded(rows: Any, names: Any, label: Any) -> list[Any]:
    """Every `section` row carrying the code this launch's label names.

    This module's own copy of the reader in `test_launch_time_provisioning.py`, for
    the reason stated above about importing across test modules.
    """
    return [row for row in rows.sections() if row.get(names.section_code_column) == label.code]


def courses_numbered(rows: Any, names: Any, ground: Any, label: Any) -> list[Any]:
    """Every `course` row for the prefix and number this launch's label names.

    Looked up by E1-10's own upsert key rather than by counting, so a writer that
    hung the course off a prefix nothing seeded fails with the row it wrote in the
    message.
    """
    prefix_column = rows.link("course", "prefix")
    return [
        row
        for row in rows.courses()
        if row.get(names.course_number_column) == label.number
        and row.get(prefix_column) == ground.prefix_id
    ]


def a_linked_person(web_identity: Any, launch_driver: Any, subject: str) -> Any:
    """One `person`, one `user` row for `subject` at this platform, and the ADR 0024 link.

    The three rows D7's seed writes for the mock world, written here for one
    subject. No assignment: which assignment this person holds is the whole
    difference between the two tests below, so it is written in the open in each of
    them rather than chosen here (`docs/MISTAKES.md` entry 30).
    """
    person_id = web_identity.person()
    user_id = web_identity.user(
        platform_id=launch_driver.registration.platform_row[web_identity.key_of("lti_platform")],
        subject=subject,
    )
    web_identity.link_person_to_user(person_id=person_id, user_id=user_id)
    return person_id


def a_launch_carrying_no_instructor_urn(launch_driver: Any, names: Any) -> Any:
    """The offer both tests drive, and the control that it is the launch they claim.

    E1-10 makes a staff launch the exact context-instructor URN and nothing else
    (ADR 0091), so a launch this door accepts and whose roles claim does not carry
    that URN is the only shape in which the leadership limb can be the thing that
    decides. The learner launch is that shape: §7.3 says a student launch triggers
    nothing, so a stored address after one can only have come from who the subject
    resolved to.
    """
    return launch_driver.offer_for_role(names.learner_role_urn)


def assert_the_launch_is_the_near_miss(signed: Any, names: Any) -> None:
    """The roles claim carries no Instructor URN, and the launch does advertise a roster.

    Both halves are controls on the question rather than assertions about the tool.
    A launch that carried the Instructor URN would provision under E1-10's rule and
    say nothing about this ticket; a launch advertising no roster address would make
    "the address was not stored" true of a launch that carried none.
    """
    roles = signed.claims.get(names.roles_claim) or []
    assert roles, (
        f"The launch this test drove carries no roles claim at all ({signed.claims.get(names.roles_claim)!r}). "
        "Then it is not the near miss this module is about and E1-08's door has nothing to "
        "dispatch on."
    )
    assert names.instructor_role_urn not in roles, (
        f"The launch carries {names.instructor_role_urn!r} outright, so it *is* a staff launch "
        "under E1-10's rule and provisioning from it says nothing about the leadership limb."
    )
    assert names.memberships_url_in(signed.claims), (
        "The launch advertises no roster service address, so 'the address was stored' and 'the "
        "address was not stored' are both statements about a launch that carried none."
    )


def test_a_leadership_persons_launch_stores_the_roster_address_with_no_instructor_urn(
    launch_driver: Any,
    provisioning_contract: Any,
    launch_ground: Any,
    provisioned_rows: Any,
    web_identity: Any,
    committed_rows: Any,
) -> None:
    """Criterion 6: the accept side of E1-10's dormant limb, activated by the linkage.

    §7.3 authorizes the trigger on the launching person's **role**, and a role in
    this system is a `role_assignment` row (§2.1, E0-09) — never a claim. So the
    question the door has to answer is "who is this subject, and what do our own
    records say they are", which is exactly what E1-12 makes answerable: `sub` →
    `user` → `person` → assignment.

    **Dies while the limb stays dormant**, which is the state E1-10 shipped
    deliberately: today this launch stores nothing, because the staff test is the
    Instructor URN alone.

    **Dies if the limb is implemented from the claim instead** — the roles claim
    here carries no Instructor URN at all, so nothing in the token distinguishes
    this launch from the student launch E1-10 already refuses to provision from.

    **Its pair is the next test**, which drives the identical launch by a subject
    whose person holds a Care assignment and requires nothing to be written. Without
    that pair, this one is equally satisfied by a door that provisions from every
    launch, which would hand a student's launch the roster of names and addresses
    §7.3 does not authorize them to reach.
    """
    offer = a_launch_carrying_no_instructor_urn(launch_driver, provisioning_contract)
    claims = launch_driver.claims_of(offer)
    label = provisioning_contract.label_of(claims)
    ground = launch_ground(label)

    person_id = a_linked_person(web_identity, launch_driver, claims[SUBJECT_CLAIM])
    committed_rows.graph.assign(LEADERSHIP_ROLE, person=person_id)
    committed_rows.commit()

    response, signed = launch_driver.launch(offer)

    launch_driver.landed(response, "a leadership person's launch")
    assert_the_launch_is_the_near_miss(signed, provisioning_contract)
    advertised = provisioning_contract.memberships_url_in(signed.claims)
    assert courses_numbered(provisioned_rows, provisioning_contract, ground, label), (
        f"No course was created for {label.prefix} {label.number}. The section this test asserts "
        "about hangs off one, so the address assertion below would be about a section that does "
        "not exist — and the launch stored nothing at all, which is the dormant limb."
    )
    sections = sections_coded(provisioned_rows, provisioning_contract, label)
    assert len(sections) == 1, (
        f"There are {len(sections)} sections coded {label.code!r} after this launch: {sections}. "
        "Zero is the limb still dormant — the launch resolved to a person holding a live "
        f"{LEADERSHIP_ROLE} assignment and discovered nothing, which is what ADR 0091 says E1-12 "
        "closes. More than one is a writer that inserts on every launch."
    )
    stored = sections[0][provisioning_contract.section_address_column]
    assert stored == advertised, (
        f"The section's `{provisioning_contract.section_address_column}` is {stored!r} and this "
        f"launch advertised {advertised!r}. §7.3 has the address arrive as a claim and be stored, "
        "and that stored address is the whole of what gives the scheduled sync its discovery: "
        "without it the section is never-synced, which §7.3 makes a state rather than a fault — "
        "and a *wrong* one is a sync pointed at somebody else's roster."
    )


def test_a_launch_by_a_linked_person_holding_no_leadership_assignment_stores_nothing(
    launch_driver: Any,
    provisioning_contract: Any,
    launch_ground: Any,
    provisioned_rows: Any,
    web_identity: Any,
    committed_rows: Any,
) -> None:
    """The refusing half: linked, assigned, and still not authorized to discover a roster.

    One row different from the test above — the assignment's role — and the answer
    is the opposite. §2.1 puts Care outside the supervision graph entirely and §7.3
    names instructors and leadership roles, so a Care officer's launch triggers
    nothing, exactly as a student's does.

    **Dies against "the subject resolves to a person, so provision"**, which is the
    natural way to write the limb once the linkage exists and is over-inclusive in
    the direction that costs the most: §7.3's own sentence is that the address is
    what hands E1-11's sync a whole section's names and email addresses, and the
    tool calls that service with its own credentials — so the launching person's
    role is the only thing standing in front of it.

    **Dies against "any live assignment triggers"**, which is the second natural
    way, and which this test poses with a real, legitimately held assignment rather
    than with an absence.

    **The positive half runs in the same environment afterwards**: an
    Instructor-URN launch has to provision here, or every assertion above is about a
    writer that does nothing rather than about the role that launched.
    """
    offer = a_launch_carrying_no_instructor_urn(launch_driver, provisioning_contract)
    claims = launch_driver.claims_of(offer)
    label = provisioning_contract.label_of(claims)
    ground = launch_ground(label)

    person_id = a_linked_person(web_identity, launch_driver, claims[SUBJECT_CLAIM])
    committed_rows.graph.assign(
        NON_LEADERSHIP_ROLE,
        scope=committed_rows.graph.scope("institution"),
        person=person_id,
        reports_to=None,
    )
    committed_rows.commit()

    response, signed = launch_driver.launch(offer)

    launch_driver.accepted(response, "a linked non-leadership person's launch")
    assert_the_launch_is_the_near_miss(signed, provisioning_contract)
    assert not courses_numbered(provisioned_rows, provisioning_contract, ground, label), (
        f"The launch created a course for {label.prefix} {label.number}. §7.3 makes the launching "
        f"person's role the authorization for what a launch triggers, and a live "
        f"{NON_LEADERSHIP_ROLE} assignment is not one of them — §2.1 puts that role outside the "
        "supervision graph altogether."
    )
    assert not sections_coded(
        provisioned_rows, provisioning_contract, label
    ), f"The launch created a section coded {label.code!r}."
    assert not provisioned_rows.addresses(), (
        f"The launch stored the roster service addresses {provisioned_rows.addresses()}. That "
        "address is what makes a later sync possible at all, so storing it here hands this "
        "section's whole roster — names and email addresses — to a sync §7.3 does not authorize."
    )

    instructor = launch_driver.offer_for_role(provisioning_contract.instructor_role_urn)
    following, following_signed = launch_driver.launch(instructor)
    launch_driver.accepted(following, "the instructor's launch that follows")
    assert provisioned_rows.addresses() == [
        provisioning_contract.memberships_url_in(following_signed.claims)
    ], (
        f"The instructor's launch into the same environment stored "
        f"{provisioned_rows.addresses()} and advertised "
        f"{provisioning_contract.memberships_url_in(following_signed.claims)!r}. Until a launch "
        "that *is* authorized stores an address here, 'no address was stored' says nothing about "
        "the role that launched — everything this environment needs is seeded."
    )
