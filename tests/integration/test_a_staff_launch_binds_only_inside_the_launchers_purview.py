"""A staff launch binds a roster address only inside the launcher's purview — E2-02.

The carried entry this module exists for (`docs/tickets/e2/carried-from-e1.md`, "A
leadership assignment anywhere is an unscoped roster-ingestion trigger", from the E1
boundary review's M9): "§7.3's leadership limb admits any holder of a live leadership
assignment as a staff-launch trigger with no reference to the launch's context: a Lead
Faculty enrolled as a Learner in a sibling lead's course can launch from it, and Pulse
binds that section, stores its roster address permanently, and pulls the full
membership — including the squat hazard on the `(course, term, section_code)` name."

Its done-when is what this module asserts: "a staff launch stores a roster address only
for a section within the launcher's resolved purview (with the first-launch case settled
and recorded), a launch outside it records a defect row rather than binding, and a
two-directional test pair pins both sides."

**Both directions live here, one row apart.** Every test below drives the same launch —
the same platform, the same context, the same roles claim — by a subject linked to a
`person` holding one live assignment. What differs between the refusing tests and the
binding ones is *which node that assignment is scoped to*, and nothing else. That is
what makes a refusal evidence about purview rather than evidence that a launch with a
Learner claim writes nothing (`docs/MISTAKES.md` entry 3), and it is what stops "refuse
every leadership launch" from passing: `docs/MISTAKES.md` entry 2 asks for the forbidden
state *and* the near miss, and the near miss here is a dean who really may bind.

**Two lines are drawn, and both are drawn in both directions.**

  - The *scope* line: an assignment that covers the launched context binds; one that
    does not is refused and recorded. Posed at two grains, because a gate written for
    one of them is a plausible partial fix — a dean over the wrong college, and a lead
    faculty over a sibling's course, which is the reported vector verbatim.
  - The *limb* line: the LTI roles claim is context-scoped, so an Instructor claim is
    staffness *of this context* and is exempt from the gate; the leadership limb reads
    our own assignment records and is not. The pair is a launch carrying the Instructor
    URN by somebody with no grant over the context (binds) beside the identical launch
    carrying only the Learner URN (refused).

**The dean's first launch is the case the design answer exists for**, and it is
asserted rather than argued: a context Pulse has never seen, no `course` row anywhere,
launched by a dean whose college contains the launched prefix, still binds. A gate that
required the launch's course or section to be inside the grant would pass every refusal
test in this module and break the one launch that bootstraps every later sync of a
brand-new course (SPEC §7.3: "the first staff launch of a section bootstraps every later
sync of it").

**Refusing the binding, not the entry.** The launch still lands the person — the
carried entry's fix is a condition on storing the discovered address, and E1-10's rule
that "a provisioning refusal NEVER fails the launch or the person's landing" is
unchanged. So each refusal test asserts the door's answer as well as the absent rows: a
test that only read the tables could not tell a launch that refused to bind from a
launch that was refused outright, and those are opposite outcomes for the person
holding the browser.

**Deliberately not marked `invariant`.** The §4.1 pass is CI's isolated run of the
confidentiality *denials*, and the E1 boundary review recorded this finding's character
in as many words: "write/ingest integrity, not a read leak — the roster is never
disclosed to the trigger, and the INSTRUCTOR row goes to the section's real teacher".
What these tests assert is that a row is not written and an address is not stored, which
is neither a read path nor a disclosure. Marking them would widen what that pass means
on the strength of a resemblance.

**Nothing about the mock's seed is transcribed.** The context label, the course number,
the section code and the roster address are read off the launch the platform signed, and
the containment chain those need is seeded from those values by `launch_ground`.

**The environment** (`docs/MISTAKES.md` entry 40): `launch_driver` builds the door
through `tool_doors` over `configured_env`, so `ENVIRONMENT` is the development name —
which is what E1-10's address rules require before the mock's own cleartext roster
address is storable at all — and `DATABASE_URL` names the session-wide testcontainers
Postgres. Every row is removed by `committed_rows`'s diff-delete.

**Its sibling module is `test_the_leadership_limb_of_a_staff_launch.py`**, which asserts
that the limb resolves through `sub` → `user` → `person` → assignment at all (E1-12's
criterion 6). This module asserts what that resolution is then allowed to do. The dean
in that module's accept test is scoped over the launched prefix's college from this
ticket on, and its docstring says why.
"""

from typing import Any

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.lti]

# `launch_driver`, `launch_ground`, `provisioning_contract` and `provisioned_rows` come
# from `tests/fixtures/provisioning.py`; `web_identity` from
# `tests/fixtures/web_identity.py`; `committed_rows` from `tests/fixtures/authz_data.py`.
# Reached as fixtures rather than imported: an import of a fixtures module by name
# depends on where pytest put `tests/` on `sys.path`, and an import error is not a red.

# The roles this module hangs on a linked person, by the spellings
# `tests/fixtures/supervision.py` resolves against the column's own enumeration.
#
# `DEAN` is §2.1's college-grain leadership role and is the one the mock world's
# launchable leader holds. `LEAD_FACULTY` is course-grain and is the carried entry's own
# actor — "a Lead Faculty enrolled as a Learner in a sibling lead's course".
# `ASSISTANT_DEAN` is §2.1's worked example of a role whose purview comes from the
# supervision graph rather than from its own scope node, and is the recorded consequence
# of building this condition out of own grants alone.
DEAN = "DEAN"
LEAD_FACULTY = "LEAD_FACULTY"
ASSISTANT_DEAN = "ASSISTANT_DEAN"

SUBJECT_CLAIM = "sub"


def a_linked_person(web_identity: Any, launch_driver: Any, subject: str) -> Any:
    """One `person`, one `user` row for `subject` at this platform, and the ADR 0024 link.

    This module's own copy of the helper in `test_the_leadership_limb_of_a_staff_launch
    .py`, for the reason stated above about importing across test modules. No assignment:
    which assignment the person holds, and which node it is scoped to, is the whole
    difference between the tests below, so each of them writes it in the open where the
    assertion can see it (`docs/MISTAKES.md` entry 30).
    """
    person_id = web_identity.person()
    user_id = web_identity.user(
        platform_id=launch_driver.registration.platform_row[web_identity.key_of("lti_platform")],
        subject=subject,
    )
    web_identity.link_person_to_user(person_id=person_id, user_id=user_id)
    return person_id


def sections_coded(rows: Any, names: Any, label: Any) -> list[Any]:
    """Every `section` row carrying the code this launch's label names."""
    return [row for row in rows.sections() if row.get(names.section_code_column) == label.code]


def courses_numbered(rows: Any, names: Any, ground: Any, label: Any) -> list[Any]:
    """Every `course` row for the prefix and number this launch's label names.

    Looked up by E1-10's own upsert key rather than by counting, so a writer that hung
    the course off a prefix nothing seeded fails with the row it wrote in the message.
    """
    prefix_column = rows.link("course", "prefix")
    return [
        row
        for row in rows.courses()
        if row.get(names.course_number_column) == label.number
        and row.get(prefix_column) == ground.prefix_id
    ]


def the_row_keyed(rows: Any, table: str, key_value: Any) -> Any:
    """The one row of `table` whose primary key is `key_value`, or a loud failure."""
    key = rows.key(table)
    found = [row for row in rows.all_of(table) if row[key] == key_value]
    assert len(found) == 1, (
        f"There are {len(found)} rows in `{table}` keyed {key_value!r}, and this reader needs "
        f"exactly one: {[dict(row) for row in found]}."
    )
    return found[0]


def the_college_walked_from_the_launched_prefix(rows: Any, ground: Any) -> Any:
    """The `college` above this launch's prefix, walked key by key in the database.

    Used by the control at the head of this module and by nothing else. Every test here
    scopes its dean with `LaunchGround.college_id`, which reads the ancestors the fixture
    built; this walks `prefix` → `department` → `college` in the rows that were actually
    written, so the control can require the two to agree. A test that took the fixture's
    word for it would be checking a fixture's bookkeeping against itself
    (`docs/MISTAKES.md` entry 19).

    A null link on the way up fails here rather than returning `None`, because a `None`
    scope would be written as an assignment scoped to nothing and every test using it
    would be asserting about a grant nobody holds.
    """
    prefix_row = the_row_keyed(rows, "prefix", ground.prefix_id)
    department_id = prefix_row[rows.link("prefix", "department")]
    assert department_id is not None, (
        f"The seeded prefix {ground.prefix_id!r} points at no department, so there is no college "
        "above it and no scope for a dean's assignment. SPEC §2.1 builds the containment "
        "hierarchy top-down and `launch_ground` seeds the chain a launch resolves against."
    )
    department_row = the_row_keyed(rows, "department", department_id)
    college_id = department_row[rows.link("department", "college")]
    assert (
        college_id is not None
    ), f"The department {department_id!r} above the launched prefix points at no college."
    return college_id


def assert_the_launch_is_the_near_miss(signed: Any, names: Any) -> None:
    """The roles claim carries no Instructor URN, and the launch does advertise a roster.

    Both halves are controls on the question rather than assertions about the tool. A
    launch carrying the Instructor URN provisions under E1-10's claim limb and says
    nothing about the leadership limb this module gates; a launch advertising no roster
    address would make "the address was not stored" true of a launch that carried none.

    This module's own copy of the check in `test_the_leadership_limb_of_a_staff_launch
    .py`, for the reason the module docstring gives about importing across test modules.
    """
    roles = signed.claims.get(names.roles_claim) or []
    assert roles, (
        f"The launch this test drove carries no roles claim at all "
        f"({signed.claims.get(names.roles_claim)!r}), so E1-08's door has nothing to dispatch on "
        "and this is not the launch the test claims to have driven."
    )
    assert names.instructor_role_urn not in roles, (
        f"The launch carries {names.instructor_role_urn!r} outright, so it is a staff launch under "
        "E1-10's claim limb and what it provisioned says nothing about the leadership limb."
    )
    assert names.memberships_url_in(signed.claims), (
        "The launch advertises no roster service address, so 'the address was not stored' and "
        "'the address was stored' are both statements about a launch that carried none."
    )


def assert_nothing_was_bound(rows: Any, names: Any, ground: Any, label: Any, what: str) -> None:
    """No course, no section and no stored address anywhere — the carried entry's done-when.

    All three, because they fail differently and each one alone is satisfiable by a
    wrong writer. A course written and a section not is a row nothing will ever complete,
    and it takes the `(course, term, section_code)` name with it — which is the squat
    hazard the carried entry names. A section written with a null address is a section
    the scheduled sync will never call but that still holds the name. And the address is
    the whole of what the carried entry is about: "the fix is a purview condition on
    storing the discovered address".

    **The section and address checks are scoped to the whole table rather than to a
    key**, deliberately, exactly as `assert_nothing_was_written` in
    `test_launch_provisioning_defects.py` is: the point of a refusal is that no row
    appeared, and a check filtered by the key the writer was supposed to use would miss a
    row written under a key it made up. The course check is by the launch's own upsert
    key so its message can name the row.
    """
    assert not courses_numbered(rows, names, ground, label), (
        f"{what} created a course for {label.prefix} {label.number}: "
        f"{[dict(row) for row in courses_numbered(rows, names, ground, label)]}. A course written "
        "for a launch whose section may not be bound is a row nothing completes, and it holds the "
        "course number against the launch that legitimately arrives next."
    )
    assert not sections_coded(rows, names, label), (
        f"{what} created a section coded {label.code!r}: "
        f"{[dict(row) for row in sections_coded(rows, names, label)]}. First-writer-wins on "
        "`(course, term, lms_section_code)` is deliberate and loud (ADR 0091), so a section "
        "bound by a launch outside the launcher's purview squats that name until an operator "
        "surface E11 has not built yet repairs it."
    )
    assert not rows.addresses(), (
        f"{what} stored the roster service addresses {rows.addresses()}. That address is what "
        "makes every later sync of this section possible (SPEC §7.3), and the tool calls the "
        "roster service with its own credentials — so storing it here hands this section's whole "
        "membership to a sync the launching person's own records do not authorize."
    )


def the_defect(rows: Any, names: Any, claims: Any, kind: str) -> Any:
    """Exactly one `launch_defect` row, of `kind`, naming this launch's own three identifiers.

    This module's own copy of the reader in `test_launch_provisioning_defects.py`. The
    identifiers are asserted against the claims rather than against constants, so a
    writer that recorded a defect for some *other* launch — the last one it saw, a
    default, an empty string — fails here. E11's admin surface reads this table to answer
    "which launches could not be ingested", and a row naming the wrong deployment sends
    somebody to the wrong LMS.

    The kind is read as well as the row's presence: a writer that recorded
    `unknown_prefix` for every refusal would satisfy a test that only counted rows, and
    the console E11 builds would then say the wrong thing about every refused launch.
    """
    recorded = rows.defects()
    assert len(recorded) == 1, (
        f"There are {len(recorded)} `{names.defect_table}` rows where there should be exactly one "
        f"of kind {kind!r}: {[dict(row) for row in recorded]}."
    )
    row = recorded[0]
    written = str(getattr(row["kind"], "value", row["kind"]))
    assert written == kind, (
        f"The recorded defect's kind is {written!r} and this launch's defect is {kind!r}. A record "
        "naming the wrong rule reads as though somebody checked, and it is the one question E11's "
        "surface exists to answer."
    )
    assert row["issuer"] == claims.get(
        "iss"
    ), f"The defect names issuer {row['issuer']!r} and the launch came from {claims.get('iss')!r}."
    assert row["deployment_id"] == claims.get(names.deployment_id_claim), (
        f"The defect names deployment {row['deployment_id']!r} and the launch carried "
        f"{claims.get(names.deployment_id_claim)!r}."
    )
    assert row["context_id"] == names.context_id_of(claims), (
        f"The defect names context {row['context_id']!r} and the launch's context claim carries id "
        f"{names.context_id_of(claims)!r}. The context id is the only handle E11 has on which "
        "course could not be ingested."
    )
    return row


def assert_the_section_holds_the_advertised_address(rows: Any, names: Any, signed: Any) -> Any:
    """Exactly one section for this launch's code, carrying the address the launch advertised."""
    sections = sections_coded(rows, names, names.label_of(signed.claims))
    assert len(sections) == 1, (
        f"There are {len(sections)} sections coded "
        f"{names.label_of(signed.claims).code!r} after this launch: "
        f"{[dict(row) for row in sections]}. Zero is a launch that was refused a binding it should "
        "have had; more than one is a writer that inserts on every launch."
    )
    advertised = names.memberships_url_in(signed.claims)
    stored = sections[0][names.section_address_column]
    assert stored == advertised, (
        f"The section's `{names.section_address_column}` is {stored!r} and this launch advertised "
        f"{advertised!r}. SPEC §7.3 has the address arrive as a claim and be stored, and that "
        "stored address is the whole of what gives the scheduled sync its discovery — without it "
        "the section is never-synced, which §7.3 makes a state rather than a fault."
    )
    return sections[0]


# ---------------------------------------------------------------------------
# The control on this module's own machinery.
# **A red here means these tests are broken, not the writer.**
# ---------------------------------------------------------------------------


def test_the_two_colleges_these_tests_are_built_out_of_are_two_different_colleges(
    launch_driver: Any,
    provisioning_contract: Any,
    launch_ground: Any,
    provisioned_rows: Any,
    committed_rows: Any,
) -> None:
    """The two scopes every pair below is built out of are proven to be two scopes.

    Each pair in this module differs by exactly one thing: whether the launcher's
    assignment is scoped over the college that contains the launched prefix, or over a
    college that does not. Both halves rest on this being a real difference, and on the
    first of them really being the college above the launched prefix.

    So three things are checked here and none of them is ceremony. `LaunchGround
    .college_id` — the scope every in-purview test uses — is required to equal the
    college reached by walking `prefix` → `department` → `college` in the rows that were
    written; without that it is a fixture's bookkeeping agreeing with itself
    (`docs/MISTAKES.md` entry 19). Both keys are required to be present, because an
    assignment scoped to `None` covers nothing and would make every direction the same
    direction. And `committed_rows.graph.scope("college")` — the scope the out-of-purview
    tests use — is required to differ from it, or those tests would be posing a dean who
    is in purview and their refusals would be coming from somewhere else entirely
    (`docs/MISTAKES.md` entry 3).

    The institution is deliberately not asserted to differ: SPEC §8 gives a deployment
    one, `uq_institution_one_row` holds it, and both chains share that row by design.

    **A red here means these tests are broken, not the writer.** Nothing here calls the
    writer at all.
    """
    offer = launch_driver.offer_for_role(provisioning_contract.learner_role_urn)
    label = provisioning_contract.label_of(launch_driver.claims_of(offer))
    ground = launch_ground(label)

    launched = ground.college_id
    walked = the_college_walked_from_the_launched_prefix(provisioned_rows, ground)
    elsewhere = committed_rows.graph.scope("college")
    committed_rows.commit()

    assert launched is not None and elsewhere is not None, (
        f"One of the two colleges is missing: the launched prefix's is {launched!r} and the "
        f"graph fixture's own is {elsewhere!r}. An assignment scoped to nothing covers nothing, "
        "and both directions of every pair below would be the same direction."
    )
    assert launched == walked, (
        f"`LaunchGround.college_id` answers {launched!r} and walking the containment keys from "
        f"the launched prefix reaches {walked!r}. Every in-purview test below scopes its dean "
        "with the first, and if it is not the college the launch's own prefix sits under then "
        "those tests are posing the out-of-purview case while claiming the opposite."
    )
    assert launched != elsewhere, (
        f"The college above the launched prefix and the college `committed_rows.graph` seeds are "
        f"both {launched!r}. Then the 'wrong college' in the tests below is the right one, and "
        "every refusal they assert would be evidence about something other than purview."
    )


# ---------------------------------------------------------------------------
# The scope line, at two grains, in both directions.
# ---------------------------------------------------------------------------


def test_a_deans_launch_into_a_context_outside_their_college_binds_nothing_and_is_recorded(
    launch_driver: Any,
    provisioning_contract: Any,
    launch_ground: Any,
    provisioned_rows: Any,
    web_identity: Any,
    committed_rows: Any,
) -> None:
    """The forbidden state: a live leadership assignment that does not reach this context.

    The carried entry's done-when, refusing half: "a launch outside it records a defect
    row rather than binding". The launcher here holds a real, live `DEAN` assignment —
    §2.1's own college-grain leadership role, and one of the roles §7.3's leadership limb
    admits — scoped over a college that does not contain the launched prefix. Nothing
    about the person is wrong; what is wrong is the context they launched from.

    **Dies against today's writer**, which admits any holder of a live leadership
    assignment "with no reference to the launch's context" — so this launch binds the
    section, stores its roster address permanently and hands the scheduled sync a class
    the launcher has no records over.

    **Dies against a gate that refuses the *launch*.** The person still lands: the
    condition is on storing the discovered address, and E1-10's rule that a provisioning
    refusal never fails the launch or the person's landing is unchanged. §2.1's table
    gives every leadership role the LTI launch, and this dean's own assignment really
    does open a door — to their own college's views, which is exactly what should
    happen.

    **Its pair is the next test**, which moves one column — the college the assignment is
    scoped to — and requires the identical launch to bind. Without that pair this test is
    equally satisfied by a writer that refuses every leadership launch, which would break
    the discovery §7.3 says the first staff launch of a section exists to perform.
    """
    offer = launch_driver.offer_for_role(provisioning_contract.learner_role_urn)
    claims = launch_driver.claims_of(offer)
    label = provisioning_contract.label_of(claims)
    ground = launch_ground(label)

    person_id = a_linked_person(web_identity, launch_driver, claims[SUBJECT_CLAIM])
    elsewhere = committed_rows.graph.scope("college")
    committed_rows.graph.assign(DEAN, scope=elsewhere, person=person_id, reports_to=None)
    committed_rows.commit()

    response, signed = launch_driver.launch(offer)

    launch_driver.landed(response, "a dean's launch into a context outside their college")
    assert_the_launch_is_the_near_miss(signed, provisioning_contract)
    assert elsewhere != ground.college_id, (
        "This dean's assignment is scoped over the college that contains the launched prefix, so "
        "the launch is inside their purview and this test is posing the accepted case. The "
        "control at the head of this module is where that is diagnosed."
    )
    assert_nothing_was_bound(
        provisioned_rows,
        provisioning_contract,
        ground,
        label,
        f"A launch by a {DEAN} scoped over another college",
    )
    the_defect(
        provisioned_rows,
        provisioning_contract,
        signed.claims,
        provisioning_contract.context_outside_purview,
    )


def test_a_deans_launch_into_a_context_inside_their_college_binds_and_stores_the_address(
    launch_driver: Any,
    provisioning_contract: Any,
    launch_ground: Any,
    provisioned_rows: Any,
    web_identity: Any,
    committed_rows: Any,
) -> None:
    """The near miss, one column apart: the same dean, scoped over the launched college.

    The carried entry's done-when, accepting half: "a staff launch stores a roster
    address only for a section within the launcher's resolved purview" — *only*, and
    still *does*. §2.1 gives a dean the college subtree as their own grant, so a launch
    from any section under that college is inside it.

    **Dies against a gate that refuses every leadership launch**, which is the cheapest
    way to pass the test above and which would break §7.3's bootstrap: "the first staff
    launch of a section bootstraps every later sync of it", and a section with no stored
    address has no roster and no sync that can be attempted.

    **Dies against a gate that reads the launch's roles claim instead of our records.**
    The claim here carries no Instructor URN, so nothing in the token distinguishes this
    launch from the student launch §7.3 triggers nothing for; the only thing that
    authorizes it is the assignment, which is what E0-09 makes a role in this system.

    **The defect table is asserted empty as well**, because a writer that bound the
    section *and* recorded a refusal would satisfy every other assertion here and leave
    E11's console reporting a fault on a launch that worked.
    """
    offer = launch_driver.offer_for_role(provisioning_contract.learner_role_urn)
    claims = launch_driver.claims_of(offer)
    label = provisioning_contract.label_of(claims)
    ground = launch_ground(label)

    person_id = a_linked_person(web_identity, launch_driver, claims[SUBJECT_CLAIM])
    committed_rows.graph.assign(DEAN, scope=ground.college_id, person=person_id, reports_to=None)
    committed_rows.commit()

    response, signed = launch_driver.launch(offer)

    launch_driver.landed(response, "a dean's launch into a context inside their college")
    assert_the_launch_is_the_near_miss(signed, provisioning_contract)
    assert courses_numbered(provisioned_rows, provisioning_contract, ground, label), (
        f"No course was created for {label.prefix} {label.number} by a dean launching inside their "
        "own college. The section this test asserts about hangs off one, so the address assertion "
        "below would be about a section that does not exist."
    )
    assert_the_section_holds_the_advertised_address(provisioned_rows, provisioning_contract, signed)
    assert not provisioned_rows.defects(), (
        f"A launch that bound correctly also recorded "
        f"{[dict(row) for row in provisioned_rows.defects()]}. The defect table is a surface a "
        "human reads and acts on; a row per successful launch makes it noise, and the refusal "
        "tests here would be satisfied by a writer that records one every time."
    )


def test_a_leads_launch_into_a_sibling_leads_course_binds_nothing_and_is_recorded(
    launch_driver: Any,
    provisioning_contract: Any,
    launch_ground: Any,
    provisioned_rows: Any,
    web_identity: Any,
    committed_rows: Any,
) -> None:
    """The reported vector, verbatim: a Lead Faculty launching from somebody else's course.

    The carried entry names this actor and no other: "a Lead Faculty enrolled as a
    Learner in a sibling lead's course can launch from it, and Pulse binds that section,
    stores its roster address permanently, and pulls the full membership". §2.1 is
    unambiguous about why that is wrong at this grain — "a Lead Faculty's grant is only
    the courses they lead (never sibling leads' courses, at any point in the union)" —
    and §4.1 invariant 2 states it as a hard invariant.

    **Posed at course grain deliberately.** The dean pair above is college grain, and a
    condition written only over the college a launcher is scoped to would pass it while
    leaving this open — the lead here is scoped to a course, and their grant is that
    course and its sections, not the prefix above it. Two grains, because the gate has to
    hold at both and one of them is a plausible partial fix.

    **`accepted` rather than `landed`**, and the reason is E1-13's landing rather than
    anything about this ticket: the door has two answers for a verified launch, the role
    route and the calm no-access page, and which one a lead faculty holding one course
    assignment gets is that ticket's rule and not this module's subject. What is asserted
    is that the door did not *refuse* the launch, which is the half E1-10's "a
    provisioning refusal never fails the launch" is about. The dean pair above asserts
    the stronger `landed` for the same reason it can: §2.1's table opens that door.
    """
    offer = launch_driver.offer_for_role(provisioning_contract.learner_role_urn)
    claims = launch_driver.claims_of(offer)
    label = provisioning_contract.label_of(claims)
    ground = launch_ground(label)

    person_id = a_linked_person(web_identity, launch_driver, claims[SUBJECT_CLAIM])
    committed_rows.graph.assign(LEAD_FACULTY, person=person_id, reports_to=None)
    committed_rows.commit()

    response, signed = launch_driver.launch(offer)

    launch_driver.accepted(response, "a lead faculty's launch into a sibling lead's course")
    assert_the_launch_is_the_near_miss(signed, provisioning_contract)
    assert_nothing_was_bound(
        provisioned_rows,
        provisioning_contract,
        ground,
        label,
        f"A launch by a {LEAD_FACULTY} who leads another course",
    )
    the_defect(
        provisioned_rows,
        provisioning_contract,
        signed.claims,
        provisioning_contract.context_outside_purview,
    )


def test_a_launch_by_an_assistant_dean_alone_binds_nothing_and_is_recorded(
    launch_driver: Any,
    provisioning_contract: Any,
    launch_ground: Any,
    provisioned_rows: Any,
    web_identity: Any,
    committed_rows: Any,
) -> None:
    """The recorded consequence of building this condition out of own grants alone.

    §2.1 makes the assistant dean the worked example of why purview comes from the
    supervision graph: "own led courses union every supervised chair's department — a set no
    single containment node holds". Their assignment's scope node is the dean's college,
    and they do **not** hold that college; transitive purview is what would resolve what
    they do hold, and it raises by design until E9 (ADR 0003).

    So a person whose only leadership assignment is `ASSISTANT_DEAN` does not pass this
    condition, and this test pins that as a consequence rather than leaving it to be
    discovered. The assignment here is scoped over the college that *contains* the
    launched prefix — the most favourable placement there is — so a green cannot come
    from having put the assignment somewhere unrelated.

    **Dies against a gate that reads the scope column's subtree for every role**, which
    is the natural over-broad reading: it would hand an assistant dean their dean's whole
    college, which is precisely the containment answer §2.1 says is the wrong one, and it
    would do it silently.

    **What this costs, stated rather than implied**, in the same direction §7.3's own
    cost argument runs: this launch discovers nothing, and the section stays unknown
    until somebody whose records reach it launches — the real instructor's next launch
    does exactly that through the claim limb, which the pair below keeps open. It is
    fail-closed, and E9 is where the graph makes it pass.
    """
    offer = launch_driver.offer_for_role(provisioning_contract.learner_role_urn)
    claims = launch_driver.claims_of(offer)
    label = provisioning_contract.label_of(claims)
    ground = launch_ground(label)

    person_id = a_linked_person(web_identity, launch_driver, claims[SUBJECT_CLAIM])
    committed_rows.graph.assign(
        ASSISTANT_DEAN, scope=ground.college_id, person=person_id, reports_to=None
    )
    committed_rows.commit()

    response, signed = launch_driver.launch(offer)

    launch_driver.accepted(response, "a launch by a person holding only an assistant deanship")
    assert_the_launch_is_the_near_miss(signed, provisioning_contract)
    assert_nothing_was_bound(
        provisioned_rows,
        provisioning_contract,
        ground,
        label,
        f"A launch by a person whose only leadership assignment is {ASSISTANT_DEAN}",
    )
    the_defect(
        provisioned_rows,
        provisioning_contract,
        signed.claims,
        provisioning_contract.context_outside_purview,
    )


# ---------------------------------------------------------------------------
# The limb line: what the LTI roles claim is allowed to authorize on its own.
# ---------------------------------------------------------------------------


def test_an_instructor_claim_binds_even_where_the_launcher_holds_no_grant_over_the_context(
    launch_driver: Any,
    provisioning_contract: Any,
    launch_ground: Any,
    provisioned_rows: Any,
    web_identity: Any,
    committed_rows: Any,
) -> None:
    """The exempt limb: an Instructor claim is staffness *of this context*, not a purview.

    The LTI roles claim is context-scoped — it says what this person is in the course
    they launched from — so a launch carrying the Instructor URN already carries the fact
    the gate is trying to establish. That is what E1-10's claim limb has always read, and
    it is what keeps §7.3's bootstrap working for the ordinary case: an instructor
    Pulse holds no assignment for launches their own section and the section is
    discovered.

    The launcher here is deliberately not a stranger: they hold a live `LEAD_FACULTY`
    assignment over a course that is not this one, which is the exact shape refused two
    tests above under a Learner claim. One member of the token differs, and the answer
    is the opposite — which is what makes this evidence about the limb rather than about
    the person.

    **Dies against a gate applied to both limbs.** That is the natural over-application:
    the condition is written once, in the one place both limbs meet, and every refusal
    test in this module passes while a real instructor's launch stops discovering their
    own section — a section with no roster, reported by §6.1's console as never-synced,
    for every course whose teacher Pulse holds no assignment for. Which is most of them.

    **`accepted` rather than `landed`** for the reason the lead faculty test above gives.
    """
    offer = launch_driver.offer_for_role(provisioning_contract.instructor_role_urn)
    claims = launch_driver.claims_of(offer)
    label = provisioning_contract.label_of(claims)
    ground = launch_ground(label)

    person_id = a_linked_person(web_identity, launch_driver, claims[SUBJECT_CLAIM])
    committed_rows.graph.assign(LEAD_FACULTY, person=person_id, reports_to=None)
    committed_rows.commit()

    response, signed = launch_driver.launch(offer)

    launch_driver.accepted(response, "an instructor-claim launch by a lead faculty of elsewhere")
    roles = signed.claims.get(provisioning_contract.roles_claim) or []
    assert provisioning_contract.instructor_role_urn in roles, (
        f"The launch this test drove carries the roles {roles!r}, which does not include "
        f"{provisioning_contract.instructor_role_urn!r}. Then it is not the claim limb's case and "
        "whatever it provisioned says nothing about the exemption."
    )
    assert courses_numbered(provisioned_rows, provisioning_contract, ground, label), (
        f"No course was created for {label.prefix} {label.number} by a launch carrying the "
        "Instructor URN. E1-10's claim limb provisions from exactly this launch, so this is the "
        "gate reaching a limb it was never meant to reach."
    )
    assert_the_section_holds_the_advertised_address(provisioned_rows, provisioning_contract, signed)
    assert not provisioned_rows.defects(), (
        f"An instructor-claim launch recorded {[dict(r) for r in provisioned_rows.defects()]}. The "
        "roles claim is context-scoped, so an Instructor claim is this person's staffness of this "
        "very context; recording it as a purview failure both refuses the discovery §7.3 depends "
        "on and tells an administrator that a working launch is broken."
    )


# ---------------------------------------------------------------------------
# The first-launch case the design answer exists for.
# ---------------------------------------------------------------------------


def test_a_deans_first_launch_into_a_course_pulse_has_never_seen_binds(
    launch_driver: Any,
    provisioning_contract: Any,
    launch_ground: Any,
    provisioned_rows: Any,
    web_identity: Any,
    committed_rows: Any,
) -> None:
    """The case the ticket makes a design answer for, asserted rather than argued.

    The ticket: "a dean's legitimate first launch into a brand-new course that no purview
    yet covers must keep working". The answer this ticket settles is that the grant is
    checked at prefix-or-below, so a dean whose college contains the launched prefix
    binds a course nothing has ever seen — which is what §7.3 needs, since "the first
    staff launch of a section bootstraps every later sync of it" and there is nothing to
    bootstrap from if the course has to exist first.

    **The precondition is asserted, not assumed.** No `course` row exists for this label
    before the launch, and that is read out of the database rather than inferred from the
    fixtures having seeded none — without it this test would be indistinguishable from
    the in-purview dean above, which runs against whatever the environment happens to
    hold (`docs/MISTAKES.md` entry 3).

    **The mutation this kills**: a gate that requires the launch's discovered course or
    bound section to be inside the grant — `covers(course_id) or covers(section_id)`,
    with the prefix left out. Every refusal in this module still passes, and the one
    launch that creates a course for the first time stops working: a brand-new course is
    in nobody's course set, by construction, because Pulse has never heard of it.

    Its opposite half is the wrong-college dean at the head of this module: the prefix is
    what makes this launch legitimate, and a prefix outside the launcher's college is
    what makes that one illegitimate. The two together say the check is on the prefix and
    on which prefix it is.
    """
    offer = launch_driver.offer_for_role(provisioning_contract.learner_role_urn)
    claims = launch_driver.claims_of(offer)
    label = provisioning_contract.label_of(claims)
    ground = launch_ground(label)

    person_id = a_linked_person(web_identity, launch_driver, claims[SUBJECT_CLAIM])
    committed_rows.graph.assign(DEAN, scope=ground.college_id, person=person_id, reports_to=None)
    committed_rows.commit()

    assert not provisioned_rows.courses(), (
        f"There are already course rows before this launch: "
        f"{[dict(row) for row in provisioned_rows.courses()]}. This test is about the launch that "
        "creates the first one, and with a course already present it asserts nothing about the "
        "first-launch case."
    )
    assert not provisioned_rows.sections(), (
        f"There are already section rows before this launch: "
        f"{[dict(row) for row in provisioned_rows.sections()]}."
    )

    response, signed = launch_driver.launch(offer)

    launch_driver.landed(response, "a dean's first launch into a brand-new course")
    assert courses_numbered(provisioned_rows, provisioning_contract, ground, label), (
        f"The dean's first launch into {label.prefix} {label.number} created no course. The prefix "
        "is inside their college, and this is the launch §7.3 relies on to discover a section at "
        "all — a gate that reaches it leaves every new course of every term never-synced, with "
        "nothing on the console saying why."
    )
    assert_the_section_holds_the_advertised_address(provisioned_rows, provisioning_contract, signed)
    assert not provisioned_rows.defects(), (
        f"A dean's first launch into a course inside their own college recorded "
        f"{[dict(r) for r in provisioned_rows.defects()]}."
    )
