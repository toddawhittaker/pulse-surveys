"""What a launch writes, and what it must not — ticket E1-10.

Acceptance criteria 1, 2 and 4, plus the scope items they rest on: the `user` row
for the launching subject, the roster service address SPEC §7.3 has a staff launch
store, and the `lms_title` fallback with its correction rules. Criterion 5 and the
defect kinds are next door in
`tests/integration/test_launch_provisioning_defects.py`; criterion 3 is
`tests/unit/test_every_writer_of_an_lms_owned_relation_names_the_guard.py`, and
the sanctioned-writer mechanism itself is
`tests/unit/test_a_sanctioned_writer_satisfies_the_chokepoint.py`.

**Driven through the door, not around it.** Every launch below travels the whole
route a browser travels — the platform's launch form at `POST /lti/login`, the
tool's own authorization request, the platform's signed answer, `POST
/lti/launch` — because E1-10's writer runs inside that request and reads the
claims that call verified. A test that handed the writer a claims dict would say
nothing about whether the launch handler calls it at all, which is half of what
this ticket is. One case cannot be posed that way and says so where it appears.

**Nothing about the mock's seed is transcribed here.** The context label, the
course number, the section code, the platform's own title and the roster address
are all read off the launch the platform signed, and the fixture rows those tests
need — a `prefix` carrying the label's prefix, a term containing the day of the
launch, a start-letter map row for the code's start position — are seeded *from*
those values by `launch_ground`. A mock that reseeds itself changes these tests'
fixture data with it rather than leaving them asserting against a course nobody
launched (`docs/MISTAKES.md` entry 19).

**Every "nothing was written" test carries its own positive half.** A student
launch storing no roster address is equally true of a tool that provisions
nothing at all, so each of the three non-staff tests drives a staff launch through
the same environment afterwards and requires the course, the section and the
address to appear. That pairing is inside the test rather than next door on
purpose: it is what makes the negative half evidence about the *role* rather than
evidence about the feature (`docs/MISTAKES.md` entry 2 — prefer asserting the
forbidden state — and entry 3 — a test that passes for an unrelated reason).

**Every launch here is asserted with `LaunchDriver.accepted` rather than `landed`,
and E1-13 is why** (`docs/MISTAKES.md` entry 22). That ticket resolves the landing
from the launching person's own live assignments, with enrollment as the student
fallback — so a launch by a subject Pulse holds nothing about is answered with the
calm no-access page, which is neither a refusal nor a role route. What these tests
have always asserted is E1-10's rule that "a provisioning refusal NEVER fails the
launch or the person's landing", and both of the door's non-refusal answers
satisfy it; `accepted` is that rule in words that stay true when the launching
person's rows entitle them to no view.

**Seeding those rows instead was tried and is unsound here**, which is worth
recording so nobody re-attempts it. Every route to a landing writes a `section`,
and the seeding helper invents a section code as `{letter}3WW` from a session-wide
counter one letter wide — so across a full run it produces `R3WW`, the very code
the mock's launch label carries, and `the_one(sections_coded(...))` then finds two
sections and fails inside its own fixture. A flake in this module would be blamed
on the writer for a week. Which *view* a launching person's rows produce is
asserted where the rows are written in the open, in
`tests/integration/test_landing_resolves_from_assignments.py`, and that a valid
launch still reaches a role route at all is asserted in
`tests/integration/test_lti_launch_door.py`.
"""

from datetime import timedelta
from typing import Any

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.lti]

# `launch_driver`, `launch_ground`, `provisioned_rows`, `provisioning_contract`,
# `provisioning` and `rows_on` all come from `tests/fixtures/provisioning.py` and
# are reached as fixtures rather than imported — an import of a fixtures module by
# name depends on where pytest put `tests/` on `sys.path`, and an import error is
# not a red. `tests/integration/test_mock_lms_launch.py` says the same at length.


def the_one(rows: list[Any], what: str) -> Any:
    """Exactly one row, or a failure that says which of the two failures happened."""
    assert len(rows) == 1, (
        f"There are {len(rows)} rows where there should be exactly one {what}: {rows}. Zero is "
        "the writer not running or refusing; more than one is an upsert that inserts every time, "
        "which no count-based idempotence check would catch either."
    )
    return rows[0]


def course_named(rows: Any, names: Any, ground: Any, label: Any) -> list[Any]:
    """Every `course` row for the prefix and number this launch's label names.

    Looked up by E1-10's own upsert key — `(prefix_id, lms_number)` — rather than
    by counting, so a writer that stored the whole label in `lms_number`, or hung
    the course off a prefix nothing seeded, fails with the row it did write in the
    message. The link to `prefix` is found by following the foreign key; see
    `ProvisionedRows.link` for why a guessed column name would turn every one of
    these filters into a filter that matches nothing.
    """
    prefix_column = rows.link("course", "prefix")
    return [
        row
        for row in rows.courses()
        if row.get(names.course_number_column) == label.number
        and row.get(prefix_column) == ground.prefix_id
    ]


def sections_coded(rows: Any, names: Any, label: Any) -> list[Any]:
    """Every `section` row carrying the code this launch's label names."""
    return [row for row in rows.sections() if row.get(names.section_code_column) == label.code]


def users_for(rows: Any, subject: Any) -> list[Any]:
    """Every `user` row keyed to one launching subject.

    `lms_user_id` is spelled by ADR 0045 — "`user.lms_user_id` is the `sub` claim
    verbatim" — and by E0-05's rule that LMS-owned columns carry the prefix.
    """
    return [row for row in rows.users() if row.get("lms_user_id") == subject]


# ---------------------------------------------------------------------------
# Criterion 1 — a staff launch against an unknown section.
# ---------------------------------------------------------------------------


def test_a_staff_launch_creates_the_course_its_context_label_names(
    launch_driver: Any,
    provisioning_contract: Any,
    launch_ground: Any,
    provisioned_rows: Any,
) -> None:
    """Criterion 1, the course half: an instructor's launch discovers a course.

    SPEC §2.1 makes courses LMS-owned with two arrival paths, "hourly roster sync
    + launch-time ingestion", and §7.3 makes the staff launch the one that
    bootstraps a section the tool has never heard of. Before this ticket nothing
    in the application wrote a `course` row at all.

    **Dies if the writer keys the course on anything but the prefix and the
    number.** The row is looked for by `(prefix_id, lms_number)` — E1-10's own
    upsert key — rather than by counting rows, so a writer that stored the whole
    label in `lms_number`, or hung the course off a prefix it invented, fails here
    with the row it did write in the message.

    **Dies if the prefix is invented rather than resolved.** `launch_ground` seeds
    exactly one `prefix`, carrying the label's own code, and §2.1 builds the org
    top-down. A launch may not create the containment chain it hangs from, and the
    paired case where the prefix is absent is
    `test_an_unknown_prefix_is_refused_and_recorded` next door.
    """
    offer = launch_driver.offer_for_role(provisioning_contract.instructor_role_urn)
    label = provisioning_contract.label_of(launch_driver.claims_of(offer))
    ground = launch_ground(label)

    response, signed = launch_driver.launch(offer)

    launch_driver.accepted(response, "an instructor's launch against an unknown section")
    course = the_one(
        course_named(provisioned_rows, provisioning_contract, ground, label),
        f"course for prefix {label.prefix!r} numbered {label.number!r}",
    )
    supplied = provisioning_contract.title_of(signed.claims)
    assert course[provisioning_contract.course_title_column] == supplied, (
        f"The course's `{provisioning_contract.course_title_column}` is "
        f"{course[provisioning_contract.course_title_column]!r} and the launch's context claim "
        f"carried the title {supplied!r}. The platform owns the title (SPEC §2.1) and this launch "
        "supplied one, so nothing here should be a fallback."
    )
    assert course[provisioning_contract.title_is_fallback_column] is False, (
        f"`{provisioning_contract.title_is_fallback_column}` is "
        f"{course[provisioning_contract.title_is_fallback_column]!r} on a course whose title came "
        "from the platform. The flag is what lets a later launch tell a real title from one this "
        "project made up, and a row marked fallback while holding a real title is the direction "
        "that loses the LMS's own value at the next launch."
    )


def test_a_staff_launch_creates_the_section_with_the_calendar_its_terms_map_gives_it(
    launch_driver: Any,
    provisioning_contract: Any,
    launch_ground: Any,
    provisioned_rows: Any,
) -> None:
    """Criterion 1, the section half: "creates course and section with correct derived dates".

    The dates are asserted against **the start-letter map row this test seeded**,
    not against a recomputation of the derivation. That is the difference between
    checking that the writer read the term's map and checking that it agrees with
    a second copy of the arithmetic: an implementation carrying its own letter
    table would agree with a recomputation and disagree with the row
    (`docs/MISTAKES.md` entry 19). ADR 0021 makes `apply_section_code` the only
    thing that may set these four columns, and E1-10's writer reaches them only
    through it — `tests/unit/test_a_sections_derived_calendar_has_one_assignment_site.py`
    is what holds that from the other side.

    The end date's inclusive convention — the last day, `start + 7 x weeks - 1` —
    is E0-07's, argued from §2.2's own seed map in
    `tests/integration/test_section_date_derivation.py`. It is restated here rather
    than re-derived: if it ever changes, that module is where it changes.

    **Dies if the section is hung on the wrong term.** Todd's ruling of
    2026-08-26: a new section belongs to the one term whose dates contain the day
    of the launch. `test_a_launch_outside_every_terms_dates_is_refused_and_recorded`
    next door holds the other side of that rule.
    """
    offer = launch_driver.offer_for_role(provisioning_contract.instructor_role_urn)
    label = provisioning_contract.label_of(launch_driver.claims_of(offer))
    ground = launch_ground(label)

    response, _ = launch_driver.launch(offer)

    launch_driver.accepted(response, "an instructor's launch against an unknown section")
    course = the_one(course_named(provisioned_rows, provisioning_contract, ground, label), "course")
    section = the_one(
        sections_coded(provisioned_rows, provisioning_contract, label),
        f"section coded {label.code!r}",
    )
    course_link = provisioned_rows.link("section", "course")
    term_link = provisioned_rows.link("section", "term")
    course_key = provisioned_rows.key("course")

    assert section[course_link] == course[course_key], (
        f"The section's `{course_link}` is {section[course_link]!r} and the course this launch "
        f"created is {course[course_key]!r}. A section under the wrong course is a section that "
        "reports against somebody else's comparison set."
    )
    assert section[term_link] == ground.term_id, (
        f"The section's `{term_link}` is {section[term_link]!r} and the term whose dates contain "
        f"the day of this launch is {ground.term_id!r}. A section in the wrong term derives its "
        "whole calendar from the wrong start-letter map."
    )
    assert section["length_weeks"] == ground.letter_length_weeks, (
        f"The section is {section['length_weeks']!r} weeks long and the start-letter map row for "
        f"`{label.start_letter}` in this term says {ground.letter_length_weeks!r}. SPEC §2.2: the "
        "start letter encodes length and start date via the per-term map, and nothing is "
        "hand-entered per section."
    )
    assert section["start_date"] == ground.letter_start, (
        f"The section starts {section['start_date']!r} and the map row for `{label.start_letter}` "
        f"starts {ground.letter_start!r}. A writer carrying its own letter table works perfectly "
        "against one institution's calendar and is wrong the first time an admin edits it."
    )
    expected_end = ground.letter_start + timedelta(days=ground.letter_length_weeks * 7 - 1)
    assert section["end_date"] == expected_end, (
        f"The section ends {section['end_date']!r} and this term's map puts its last day at "
        f"{expected_end!r}. E0-07's convention is the inclusive one, argued from §2.2's own seed "
        "map in `tests/integration/test_section_date_derivation.py`, which is where it changes if "
        "it ever does."
    )


def test_a_staff_launch_stamps_the_section_with_the_context_it_was_discovered_from(
    launch_driver: Any,
    provisioning_contract: Any,
    launch_ground: Any,
    provisioned_rows: Any,
) -> None:
    """The round-3 binding: a section records which context, on which deployment, made it.

    The security review's HIGH turned on a section having no identity of its own.
    It was resolved by what its label parsed to — prefix, number, section code —
    and a course copy keeps the section code, so a launch from the copy resolved
    the original and repointed its roster address. The fix gives `section` an
    identity the platform owns: `lms_context_id`, the context claim's `id`, unique
    within `lti_deployment_id`, the registration the launch resolved to.

    This is the positive half. The refusals it makes possible are in
    `tests/integration/test_a_launch_may_not_repoint_another_contexts_section.py`,
    and every one of them is satisfied by a writer that provisions nothing — which
    is what this test, and the two it sits beside, rule out.

    **Both halves of the pair are asserted**, because either alone is a binding
    that does not bind. A section stamped with the context and not the deployment
    is unique across the world, so two institutions whose platforms hand out the
    same context identifier share a section; a section stamped with the deployment
    and not the context is every section of that deployment at once.

    **Dies if either column is written from anywhere but the launch.** The context
    id is compared against the claim the platform signed and the deployment
    against the row this suite registered for it, with those two checked against
    each other first — so a stamp that matched by both being wrong in the same way
    is not read as a stamp that matched.
    """
    offer = launch_driver.offer_for_role(provisioning_contract.instructor_role_urn)
    label = provisioning_contract.label_of(launch_driver.claims_of(offer))
    launch_ground(label)

    response, signed = launch_driver.launch(offer)

    launch_driver.accepted(response, "an instructor's launch against an unknown section")
    registration = launch_driver.registration
    assert registration is not None, (
        "The launch driver carries no registration, so this test has nothing to compare the "
        "section's deployment against. `launch_driver_in` in tests/fixtures/provisioning.py is "
        "where the registered rows are kept."
    )
    claimed_deployment = signed.claims.get(provisioning_contract.deployment_id_claim)
    assert claimed_deployment == registration.deployment_id, (
        f"The launch claims deployment {claimed_deployment!r} and the row this suite registered "
        f"carries {registration.deployment_id!r}. They have to be the same deployment, or the "
        "comparison below is between two unrelated values and would be satisfied by a stamp taken "
        "from anywhere at all."
    )

    section = the_one(
        sections_coded(provisioned_rows, provisioning_contract, label),
        f"section coded {label.code!r}",
    )
    context_id = provisioning_contract.context_id_of(signed.claims)
    stamped = section[provisioning_contract.section_context_id_column]
    assert stamped == context_id, (
        f"The section's `{provisioning_contract.section_context_id_column}` is {stamped!r} and the "
        f"launch's context claim carries id {context_id!r}. That value is the one thing about a "
        "section that the platform owns and a course copy does not reproduce — a section stamped "
        "with anything else is resolvable by a launch that has no business finding it."
    )
    deployment_link = provisioned_rows.link("section", "lti_deployment")
    registered_key = registration.deployment_row[provisioned_rows.key("lti_deployment")]
    assert section[deployment_link] == registered_key, (
        f"The section's `{deployment_link}` is {section[deployment_link]!r} and the deployment "
        f"this launch resolved to is {registered_key!r}. A context id is unique within a "
        "deployment and not across the world, so without this half two institutions' platforms "
        "handing out one identifier share a section."
    )


def test_a_staff_launch_stores_the_roster_service_address_from_its_own_claim(
    launch_driver: Any,
    provisioning_contract: Any,
    launch_ground: Any,
    provisioned_rows: Any,
) -> None:
    """SPEC §7.3's stored address, which is what gives the scheduled sync its discovery.

    "The roster service address arrives as a claim on that launch and is
    **stored**, which is what gives the scheduled job the discovery it otherwise
    lacks — it has no way of its own to learn that a section exists. So the first
    staff launch of a section bootstraps every later sync of it."

    **Asserted against the launch's own NRPS claim**, so a writer that built the
    address out of the issuer and a guessed path fails: the value has to have been
    read from the token. E1-11 is what calls it; nothing here dispatches a sync,
    and this ticket's scope says so.
    """
    offer = launch_driver.offer_for_role(provisioning_contract.instructor_role_urn)
    label = provisioning_contract.label_of(launch_driver.claims_of(offer))
    launch_ground(label)

    response, signed = launch_driver.launch(offer)

    launch_driver.accepted(response, "an instructor's launch")
    advertised = provisioning_contract.memberships_url_in(signed.claims)
    section = the_one(
        sections_coded(provisioned_rows, provisioning_contract, label),
        f"section coded {label.code!r}",
    )
    stored = section[provisioning_contract.section_address_column]
    assert stored == advertised, (
        f"The section's `{provisioning_contract.section_address_column}` is {stored!r} and the "
        f"launch advertised {advertised!r} under `{provisioning_contract.nrps_claim}`. §7.3 has "
        "the address arrive as a claim and be stored; a section with the wrong address is a sync "
        "pointed at somebody else's roster, and a section with none is §7.3's never-synced state, "
        "which is a different thing entirely."
    )


def test_a_second_identical_staff_launch_changes_no_row(
    launch_driver: Any,
    provisioning_contract: Any,
    launch_ground: Any,
    provisioned_rows: Any,
) -> None:
    """Criterion 1: "a second identical launch changes nothing (asserted on row identity)".

    Row identity rather than count, which the criterion asks for by name and which
    is the whole of the difference. Two shapes of wrong implementation pass a
    count: an upsert that rewrites every column on every launch — same row, new
    values, and on `course` that means the LMS's title rewritten by whatever the
    latest launch happened to carry — and one that deletes and reinserts, which
    gives the section a new primary key and orphans everything E2 hangs off it.
    Comparing the whole mapping catches both.

    **What this does not pin** is the upsert key: a writer keyed on the context
    `id` rather than on `(prefix_id, lms_number)` and `(course_id, term_id,
    lms_section_code)` passes here.
    `test_a_staff_launch_creates_the_course_its_context_label_names` is what pins
    it, by looking the row up by that key; what this one adds is that a second
    launch finds it.
    """
    offer = launch_driver.offer_for_role(provisioning_contract.instructor_role_urn)
    label = provisioning_contract.label_of(launch_driver.claims_of(offer))
    ground = launch_ground(label)

    def snapshot() -> dict[str, Any]:
        return {
            "course": dict(
                the_one(
                    course_named(provisioned_rows, provisioning_contract, ground, label), "course"
                )
            ),
            "section": dict(
                the_one(sections_coded(provisioned_rows, provisioning_contract, label), "section")
            ),
        }

    first, _ = launch_driver.launch(offer)
    launch_driver.accepted(first, "the first instructor launch")
    after_one = snapshot()

    second, _ = launch_driver.launch(offer)
    launch_driver.accepted(second, "a second identical instructor launch")
    after_two = snapshot()

    assert after_two == after_one, (
        "A second identical launch changed a row.\n"
        f"  after the first: {after_one}\n"
        f"  after the second: {after_two}\n"
        "Criterion 1 asks for idempotence on row identity: the same primary key and the same "
        "values. A changed key is a delete-and-reinsert, which orphans every row a later epic "
        "hangs off this section; a changed value on `course` is the LMS's own title being "
        "overwritten on every launch."
    )


def test_a_launch_creates_the_launching_subjects_user_row_once(
    launch_driver: Any,
    provisioning_contract: Any,
    launch_ground: Any,
    provisioned_rows: Any,
) -> None:
    """The scope item ADR 0045 already called a sanctioned write: `sub` becomes a `user` row.

    ADR 0045 puts `user` in the guarded set because "`user.lms_user_id` is the
    `sub` claim verbatim (ADR 0014: the platform supplies the value and Pulse
    never edits it) and §4 keys every response to it", and names "the launch path
    that creates a `user` row" as the sanctioned writer. This is that writer.

    **Insert-if-absent and never updated**, so two launches leave one row, value
    for value. A row rewritten on each launch is a `sub` this project has edited,
    which is exactly what the `lms_` marker says never happens.

    **This test used to say it was about a launch that lands, and E1-13 made that
    impossible to keep.** It has a second reason for `accepted` beyond the
    module-wide one above: from that ticket a landing comes from an assignment or
    an enrollment, and an enrollment hangs off the very `user` row this test exists
    to watch being created. So even where seeding were otherwise sound, seeding it
    here would be handing back the answer (`docs/MISTAKES.md` entry 30) — and a
    *first* launch by anybody reaches the calm no-access page by construction.
    """
    offer = launch_driver.offer_for_role(provisioning_contract.learner_role_urn)
    label = provisioning_contract.label_of(launch_driver.claims_of(offer))
    launch_ground(label)

    first, signed = launch_driver.launch(offer)
    launch_driver.accepted(first, "a first launch by a subject Pulse holds no rows for")
    subject = signed.claims.get("sub")
    assert subject, "The launch carries no `sub`, so there is no subject for a `user` row to be."
    created = the_one(
        users_for(provisioned_rows, subject), f"`user` row for the subject {subject!r}"
    )

    second, _ = launch_driver.launch(offer)
    launch_driver.accepted(second, "the same person's second launch")
    again = the_one(
        users_for(provisioned_rows, subject),
        f"`user` row for {subject!r} after a second launch",
    )

    assert dict(again) == dict(created), (
        f"The second launch changed the `user` row.\n  before: {dict(created)}\n"
        f"  after: {dict(again)}\n"
        "E1-10 inserts this row if it is absent and never updates it: `lms_user_id` is the `sub` "
        "claim verbatim, and ADR 0014's marker means the platform supplies the value and Pulse "
        "never writes over it."
    )


# ---------------------------------------------------------------------------
# Criterion 2 — the launches that trigger nothing. Each carries its own
# positive half.
# ---------------------------------------------------------------------------


def assert_nothing_was_provisioned(
    rows: Any, names: Any, ground: Any, label: Any, who: str
) -> None:
    """No course, no section and no roster address anywhere, after `who` launched.

    The forbidden state rather than the permitted one (`docs/MISTAKES.md` entry
    2), and asserted three ways because the three failures are different: a course
    written for a launch that may not discover one, a section written under it,
    and — the one §7.3 cares about most — a roster address stored, which is what
    would hand E1-11's sync the roster of names and email addresses §7.3 does not
    authorize this person to reach.

    The address check is over *every* section rather than over the one this label
    names, because a writer that stored the address on a section it created under
    some other key would satisfy a narrower check.
    """
    assert not course_named(rows, names, ground, label), (
        f"{who} created a course for {label.prefix} {label.number}. SPEC §7.3 makes the launching "
        "person's role the authorization for what a launch triggers, and this role is not one of "
        "them."
    )
    assert not sections_coded(rows, names, label), f"{who} created a section coded {label.code!r}."
    assert not rows.addresses(), (
        f"{who} stored the roster service addresses {rows.addresses()}. §7.3: 'a launch by an "
        "instructor or any leadership role triggers a roster sync' and 'a **student** launch does "
        "not'. The address is what makes a later sync possible at all, so storing it here hands "
        "this section's whole roster — names and email addresses — to a sync nobody authorized."
    )


def assert_a_staff_launch_still_provisions(
    driver: Any, rows: Any, names: Any, ground: Any, label: Any
) -> None:
    """The positive half, run in the same environment after the negative one.

    Without this, every "nothing was written" assertion above is equally true of a
    tool that provisions nothing at all — which is precisely the state of this
    repository on the day these tests are written. It is the difference between
    evidence about the *role* and evidence about the feature
    (`docs/MISTAKES.md` entry 3).
    """
    response, signed = driver.launch(driver.offer_for_role(names.instructor_role_urn))
    driver.accepted(response, "the instructor's launch that follows")

    assert course_named(rows, names, ground, label), (
        "The instructor's launch into the same environment created no course either, so the "
        "assertions above are about a writer that does nothing rather than about the role that "
        "launched. Everything this environment needs is seeded: the prefix, a term containing "
        "today, and a start-letter map row for this code."
    )
    advertised = names.memberships_url_in(signed.claims)
    assert rows.addresses() == [advertised], (
        f"The instructor's launch stored {rows.addresses()} and its own NRPS claim advertised "
        f"{advertised!r}. Until a staff launch stores an address in this environment, 'no address "
        "was stored' says nothing about the role."
    )


def test_a_student_launch_stores_no_roster_address_and_creates_no_course_or_section(
    launch_driver: Any,
    provisioning_contract: Any,
    launch_ground: Any,
    provisioned_rows: Any,
) -> None:
    """Criterion 2: "a student launch ... stores no roster address and triggers no sync".

    §7.3 states it as a rule about who launched, not about what was asked for:
    "The tool calls the roster service with its own credentials, so the launching
    person's role authorizes the *trigger*, never the request." A student's launch
    carries the same NRPS claim an instructor's does — a platform advertises its
    services on every launch — so the address is *there* and the tool declines to
    keep it. That is why the assertion is about the stored value and not about the
    claim, and why the claim's presence is asserted first.

    **The canary is the student's own `user` row**: E1-10 writes one on every
    launch that lands, so its presence says provisioning ran and chose not to
    write the rest, rather than that nothing ran at all. The staff launch
    afterwards is the second, stronger half.
    """
    student = launch_driver.offer_for_role(provisioning_contract.learner_role_urn)
    label = provisioning_contract.label_of(launch_driver.claims_of(student))
    ground = launch_ground(label)

    response, signed = launch_driver.launch(student)

    launch_driver.accepted(response, "a student's launch against an unknown section")
    assert provisioning_contract.memberships_url_in(signed.claims), (
        "The student's own launch advertises no roster service address, so 'the address was not "
        "stored' is true of a launch that carried none and says nothing about the rule."
    )
    subject = signed.claims.get("sub")
    assert users_for(provisioned_rows, subject), (
        f"No `user` row was created for the student who launched ({subject!r}), so provisioning "
        "did not run at all and the three assertions below are about a feature that is absent "
        "rather than about a student launch."
    )
    assert_nothing_was_provisioned(
        provisioned_rows, provisioning_contract, ground, label, "A student's launch"
    )
    assert_a_staff_launch_still_provisions(
        launch_driver, provisioned_rows, provisioning_contract, ground, label
    )


def test_a_teaching_assistant_launch_stores_no_roster_address_and_creates_no_course_or_section(
    launch_driver: Any,
    provisioning_contract: Any,
    launch_ground: Any,
    provisioned_rows: Any,
) -> None:
    """Criterion 2's near miss: a roles claim whose only URN contains the string "Instructor".

    E1-10's scope makes the staff test an **exact string match** on
    `http://purl.imsglobal.org/vocab/lis/v2/membership#Instructor` and says why in
    one line: "never substring, because the TeachingAssistant sub-role URN embeds
    the word Instructor". E1-07 minted `only_teaching_assistant_role` for exactly
    this test, and its own artifact test asserts the URN really does contain the
    substring.

    **This is the most valuable test in the module**, because the wrong
    implementation is the natural one — `any("Instructor" in role for role in
    roles)` — and it is correct on every launch a developer tries by hand. What it
    costs is §7.3's authorization boundary: over-inclusion "hands a TA the full
    roster — names and emails — that §7.3 does not authorize".

    **No `user` row is asserted either way.** E1-08's door has no view for this
    role and refuses the launch, so whether provisioning runs before that refusal
    is a question this ticket does not settle. The positive half below is what
    makes the negative assertions mean something instead.
    """
    instructor = launch_driver.offer_for_role(provisioning_contract.instructor_role_urn)
    label = provisioning_contract.label_of(launch_driver.claims_of(instructor))
    ground = launch_ground(label)

    _, signed = launch_driver.launch(
        instructor, defect=provisioning_contract.only_teaching_assistant_role
    )

    roles = signed.claims.get(provisioning_contract.roles_claim) or []
    assert roles and all("Instructor" in role for role in roles), (
        f"The launch this test drove carries roles {roles}, and not every one of them contains "
        "the string 'Instructor'. Then it is not the near miss this test is named for: any "
        "implementation that reads the roles claim at all refuses it, and the substring trap goes "
        "untested."
    )
    assert provisioning_contract.instructor_role_urn not in roles, (
        f"The launch carries {provisioning_contract.instructor_role_urn!r} outright, so it *is* a "
        "staff launch and E1-10 is right to provision from it. `only_teaching_assistant_role` is "
        "supposed to carry the sub-role URN alone."
    )
    assert_nothing_was_provisioned(
        provisioned_rows,
        provisioning_contract,
        ground,
        label,
        "A launch whose only role is the TeachingAssistant sub-role",
    )
    assert_a_staff_launch_still_provisions(
        launch_driver, provisioned_rows, provisioning_contract, ground, label
    )


def test_a_mentor_launch_stores_no_roster_address_and_creates_no_course_or_section(
    launch_driver: Any,
    provisioning_contract: Any,
    launch_ground: Any,
    provisioned_rows: Any,
) -> None:
    """Criterion 2's third case: a real LIS role that is nobody's staff.

    A mentor is a parent or an advisor watching a learner. The URN is from the
    same membership vocabulary the recognised roles come from, so this is a well
    formed launch by somebody this system has nothing to show — and handing that
    person's launch the power to bootstrap a roster sync would be §7.3's boundary
    read as "anyone who is not a student".

    Paired with the TeachingAssistant case above rather than folded into it: the
    two fail different implementations. A substring match on "Instructor" passes
    this one and fails that one; a rule of "not a Learner" fails both.
    """
    instructor = launch_driver.offer_for_role(provisioning_contract.instructor_role_urn)
    label = provisioning_contract.label_of(launch_driver.claims_of(instructor))
    ground = launch_ground(label)

    _, signed = launch_driver.launch(instructor, defect=provisioning_contract.only_mentor_role)

    roles = signed.claims.get(provisioning_contract.roles_claim) or []
    assert roles and provisioning_contract.instructor_role_urn not in roles, (
        f"The launch this test drove carries roles {roles}. `only_mentor_role` is supposed to "
        "carry the Mentor URN alone, and a launch that still carries the Instructor URN is a "
        "staff launch this test would be wrong to forbid."
    )
    assert_nothing_was_provisioned(
        provisioned_rows,
        provisioning_contract,
        ground,
        label,
        "A launch whose only role is Mentor",
    )
    assert_a_staff_launch_still_provisions(
        launch_driver, provisioned_rows, provisioning_contract, ground, label
    )


# ---------------------------------------------------------------------------
# Criterion 4, as reworded on 2026-08-26 — the title, its fallback, and the
# corrections in all three directions.
# ---------------------------------------------------------------------------


def test_a_context_with_a_label_and_no_title_provisions_the_fallback_title(
    launch_driver: Any,
    provisioning_contract: Any,
    launch_ground: Any,
    provisioned_rows: Any,
) -> None:
    """Criterion 4 as reworded: the with-label mint is what proves the fallback.

    `course.lms_title` is `NOT NULL` (E0-05) and a platform is entitled to send a
    context with no title, so a value has to come from somewhere. Todd's ruling of
    2026-08-26: "'BIOL 215' style — prefix and number parsed from the label —
    marked as a fallback so a later real title replaces it and a real title is
    never overwritten by a fallback." The id-alone mint proves the other half of
    that ruling and is asserted next door: it identifies no course at all and is
    refused and recorded.

    **Both halves are asserted, and the flag is the load-bearing one.** A writer
    that stored the right string and left `title_is_fallback` false would pass a
    test that only read the title, and would have made this project's guess
    indistinguishable from the LMS's own value — after which neither correction
    test below can be satisfied by any implementation at all.
    """
    offer = launch_driver.offer_for_role(provisioning_contract.instructor_role_urn)
    label = provisioning_contract.label_of(launch_driver.claims_of(offer))
    ground = launch_ground(label)

    response, signed = launch_driver.launch(
        offer, defect=provisioning_contract.titleless_context_with_label
    )

    launch_driver.accepted(response, "a launch whose context carries a label and no title")
    assert "title" not in provisioning_contract.context_of(signed.claims), (
        "The launch this test drove still carries a context `title`, so the fallback is never "
        "reached and this test would pass against a writer that has none."
    )
    course = the_one(course_named(provisioned_rows, provisioning_contract, ground, label), "course")
    expected = provisioning_contract.fallback_title(label)
    assert course[provisioning_contract.course_title_column] == expected, (
        f"The course's title is {course[provisioning_contract.course_title_column]!r} and the "
        f"fallback this ticket decided is {expected!r} — the label's prefix and number, spelled "
        "the way SPEC §2.1 spells a course ('BIOL 215')."
    )
    assert course[provisioning_contract.title_is_fallback_column] is True, (
        f"`{provisioning_contract.title_is_fallback_column}` is "
        f"{course[provisioning_contract.title_is_fallback_column]!r} on a course whose title this "
        "project invented. Unmarked, the guess is indistinguishable from the LMS's own value, and "
        "no later launch or sync can tell whether it is safe to replace."
    )


def test_a_real_title_arriving_later_replaces_a_fallback_and_clears_the_flag(
    launch_driver: Any,
    provisioning_contract: Any,
    launch_ground: Any,
    provisioned_rows: Any,
) -> None:
    """The first correction direction: a fallback is a placeholder, and it gives way.

    E1-10's scope: the fallback "is distinguishable from a platform-supplied title
    (the ADR says how, so a later sync does not 'correct' a real title into a
    fallback or vice versa)". This is the *or vice versa* half — a course
    discovered from a titleless launch, then launched again from a context that
    carries its title. The flag has to clear with the value, or the next titleless
    launch would read the real title as a fallback and overwrite it.

    The pair to this is the test directly below, which drives the same two launches
    in the other order and requires the opposite outcome. Neither is worth anything
    alone: a writer that always overwrites passes this one, and a writer that never
    overwrites passes that one.
    """
    offer = launch_driver.offer_for_role(provisioning_contract.instructor_role_urn)
    label = provisioning_contract.label_of(launch_driver.claims_of(offer))
    ground = launch_ground(label)
    key = provisioned_rows.key("course")

    first, _ = launch_driver.launch(
        offer, defect=provisioning_contract.titleless_context_with_label
    )
    launch_driver.accepted(first, "a titleless launch")
    fallback = the_one(
        course_named(provisioned_rows, provisioning_contract, ground, label), "course"
    )
    assert fallback[provisioning_contract.title_is_fallback_column] is True, (
        "The first launch did not leave a fallback title, so this test is not starting from the "
        "state it is about. `test_a_context_with_a_label_and_no_title_provisions_the_fallback_"
        "title` is where that is diagnosed."
    )

    second, signed = launch_driver.launch(offer)
    launch_driver.accepted(second, "a later launch carrying the platform's own title")

    corrected = the_one(
        course_named(provisioned_rows, provisioning_contract, ground, label), "course"
    )
    supplied = provisioning_contract.title_of(signed.claims)
    assert corrected[key] == fallback[key], (
        "The second launch created a different course row rather than correcting the first. The "
        "upsert key is `(prefix_id, lms_number)`, and both launches name the same pair."
    )
    assert corrected[provisioning_contract.course_title_column] == supplied, (
        f"The course still holds {corrected[provisioning_contract.course_title_column]!r} after a "
        f"launch carrying the platform's title {supplied!r}. SPEC §2.1 makes the LMS the owner of "
        "a course's title; a fallback is a placeholder until the owner supplies one."
    )
    assert corrected[provisioning_contract.title_is_fallback_column] is False, (
        f"`{provisioning_contract.title_is_fallback_column}` is still "
        f"{corrected[provisioning_contract.title_is_fallback_column]!r} after a real title "
        "arrived. A real title left marked as a fallback is one a later titleless launch will "
        "overwrite, which is the failure the flag exists to prevent."
    )


def test_a_titleless_launch_never_overwrites_a_title_the_platform_supplied(
    launch_driver: Any,
    provisioning_contract: Any,
    launch_ground: Any,
    provisioned_rows: Any,
) -> None:
    """The second correction direction, and the one with a cost attached.

    The same two launches as the test above, in the other order. A writer that
    simply writes whatever title it computed on every launch passes that test and
    fails this one — and the failure it would ship is quiet in exactly the way ADR
    0045 describes: the LMS's own course title replaced by "BIOL 215" on every
    screen in the product, with nothing erroring and no sync undoing it, because
    Pulse is the thing that wrote it.
    """
    offer = launch_driver.offer_for_role(provisioning_contract.instructor_role_urn)
    label = provisioning_contract.label_of(launch_driver.claims_of(offer))
    ground = launch_ground(label)

    first, signed = launch_driver.launch(offer)
    launch_driver.accepted(first, "a launch carrying the platform's own title")
    real_title = provisioning_contract.title_of(signed.claims)
    stored = the_one(course_named(provisioned_rows, provisioning_contract, ground, label), "course")
    assert stored[provisioning_contract.course_title_column] == real_title, (
        "The first launch did not store the platform's title, so this test is not starting from "
        "the state it is about."
    )
    assert real_title != provisioning_contract.fallback_title(label), (
        f"The platform's own title for this context is {real_title!r}, which is the same string "
        f"as the fallback {provisioning_contract.fallback_title(label)!r}. Then no assertion "
        "below can tell an overwrite from a no-op, and this test proves nothing."
    )

    second, _ = launch_driver.launch(
        offer, defect=provisioning_contract.titleless_context_with_label
    )
    launch_driver.accepted(second, "a later launch whose context carries no title")

    after = the_one(course_named(provisioned_rows, provisioning_contract, ground, label), "course")
    assert after[provisioning_contract.course_title_column] == real_title, (
        f"A titleless launch replaced the platform's title {real_title!r} with "
        f"{after[provisioning_contract.course_title_column]!r}. SPEC §2.1 makes course titles "
        "LMS-owned and §8 says LMS-owned data is never hand-edited in Pulse — a fallback written "
        "over a real title is this project editing it."
    )
    assert after[provisioning_contract.title_is_fallback_column] is False, (
        f"`{provisioning_contract.title_is_fallback_column}` was set on a course still holding "
        "the platform's own title. The flag says where the value came from, so setting it here "
        "invites the next launch to overwrite a title nobody may overwrite."
    )


def test_a_changed_platform_title_replaces_the_stored_one(
    launch_driver: Any,
    provisioning: Any,
    provisioning_contract: Any,
    launch_ground: Any,
    rows_on: Any,
    db_session: Any,
) -> None:
    """The third correction direction: the LMS renamed the course, and Pulse follows.

    SPEC §2.1 makes the title LMS-owned, so a *different* real title is not a
    conflict to preserve — it is the owner's new value, and a tool that kept the
    old one would be showing a course name the institution has retired.

    **This one case is driven at the writer rather than through the door**, and
    that is a limitation of the fixtures rather than a choice: the mock platform
    mints one title per context, so a second, different *platform* title cannot be
    produced through a launch. The claims are still a real launch's — minted by
    the same platform every other test here launches from, and registered the same
    way — with the context claim's `title` as the only member changed, so what the
    writer is handed differs from what a door would hand it in exactly that one
    place (`docs/MISTAKES.md` entry 37: say which properties of the runtime the
    harness reproduces and which it does not; this one does not reproduce the
    handler that calls the writer, which every other test in this module does).
    """
    offer = launch_driver.offer_for_role(provisioning_contract.instructor_role_urn)
    original = launch_driver.claims_of(offer)
    label = provisioning_contract.label_of(original)
    launch_ground(label)
    rows = rows_on(db_session)
    key = rows.key("course")

    provisioning.call(provisioning.provision, session=db_session, claims=original)
    first = the_one(rows.courses(), "course after the first launch")
    stored_title = provisioning_contract.title_of(original)
    assert first[provisioning_contract.course_title_column] == stored_title, (
        "The first call did not store the platform's title, so this test is not starting from the "
        "state it is about."
    )

    renamed = dict(original)
    context = provisioning_contract.context_of(original)
    context["title"] = f"{stored_title} (renamed by the platform)"
    renamed[provisioning_contract.context_claim] = context

    provisioning.call(provisioning.provision, session=db_session, claims=renamed)

    after = the_one(rows.courses(), "course after the renamed launch")
    assert after[key] == first[key], (
        "The renamed launch created a second course rather than updating the first. The upsert "
        "key is `(prefix_id, lms_number)` and neither of those changed."
    )
    assert after[provisioning_contract.course_title_column] == context["title"], (
        f"The course still holds {after[provisioning_contract.course_title_column]!r} after the "
        f"platform sent {context['title']!r}. The LMS owns the title, so a changed real title is "
        "the owner's new value and not a conflict to preserve."
    )
    assert (
        after[provisioning_contract.title_is_fallback_column] is False
    ), "A course holding a title the platform supplied was marked as carrying a fallback."
