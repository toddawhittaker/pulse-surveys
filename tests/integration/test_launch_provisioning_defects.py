"""What a launch is refused for, and what gets written down — ticket E1-10.

Acceptance criterion 5 — "an out-of-band course number is refused and recorded;
nothing is written" — generalised to the defect kinds this ticket's design
enumerates, plus the record's own field set. Criteria 1, 2 and 4 are next door in
`tests/integration/test_launch_time_provisioning.py`.

**The set is nine, and five of them are here.** Round 3's security review added
two, E2-02 added a third and E3-02 a fourth, and each is asserted where its own
subject is: `context_collision` in
`tests/integration/test_a_launch_may_not_repoint_another_contexts_section.py`,
`roster_address_refused` in
`tests/integration/test_a_roster_address_is_judged_by_the_registration_rules.py`,
`context_outside_purview` in
`tests/integration/test_a_staff_launch_binds_only_inside_the_launchers_purview.py`,
and `ags_address_refused` in
`tests/integration/test_a_launch_stores_the_gradebook_address_it_was_given.py`.
What stays here is everything that judges *what the label said* — and the two
tests at the foot of this file, which pin the closed set and the record's fields
for all nine.

**Every one of these is a launch that still lands.** E1-10's work order: "A
provisioning refusal NEVER fails the launch or the person's landing: the write is
skipped, the defect row is written and committed." So each test below asserts
three things and not one — the launch was accepted, nothing was written, and the
record says which rule fired. Dropping the third is `docs/MISTAKES.md` entry 26
exactly, a fallback path swallowing the defect that triggered it; dropping the
first turns a data-quality problem into a person who cannot get in.

**What "still lands" becomes since E1-13** (`docs/MISTAKES.md` entry 22). That
ticket resolves the landing from the launching person's own live assignments, so a
launch by a subject Pulse holds nothing about is answered with the calm no-access
page — which is not a refusal, and is not a landing either. So the first of the
three assertions is `LaunchDriver.accepted` rather than `landed` throughout this
module: the door verified the token and did not refuse, which is exactly what
E1-10's "a provisioning refusal NEVER fails the launch" asks, and which of the
door's two answers the person got is not this module's subject.

**It is `accepted` rather than seeded rows, and the reason is this file's own
strictness.** The sibling module `test_launch_time_provisioning.py` repairs the
same breakage by seeding the launching subject a landing. That is unavailable
here: `assert_nothing_was_written` asserts that `course` and `section` are
*entirely empty* — deliberately, because "a check filtered by the key the writer
was supposed to use would miss a row written under a key it made up" — and every
route to a landing writes into at least one of them, since an instructor
assignment is scoped to a section and an enrollment needs one. Seeding would make
criterion 5's own assertion unstatable.

**The kind is asserted, not merely the presence of a row.** A defect is a defect:
a writer that recorded `unknown_prefix` for every refusal would satisfy a test
that only counted rows, and the admin surface E11 builds on this would then say
the wrong thing about every launch. `the_defect` below reads the kind and the
three identifiers, and the four cases that can be posed through the door are posed
by removing exactly one thing from an environment that is otherwise complete —
which is what makes each kind attributable to its own cause.

**Four cases are driven through the door and one is not.** Three of the five
defects are properties of the *environment* — no prefix, no term containing the
day of the launch, no start-letter map row for this code — so they are posed by
seeding one thing differently and launching for real. The fourth,
`unparseable_context_label`, is E1-07's `titleless_context` mint. Only the course
number cannot be posed that way: nothing mints a launch carrying an out-of-band
number and E1-07's mint list is closed, so the band cases rewrite one member of a
real launch's claims and hand them to the writer. `registered_platform` and
`with_course_number` are that arrangement, and the control on the rewrite is the
first test in that section.
"""

from typing import Any

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.lti]

# SPEC §8's bands, as the numbers on either side of every edge they have.
#
# "Width is part of the rule, not an accident of it: a three-digit number is valid
# only in `000`-`799`, and a four-digit number only in `8000`-`9999`. So `800` and
# `999` are rejected, and so are `1000`-`7999` and any four-digit number below
# `1000`. That last case is why width is stated rather than left to the
# arithmetic — `0099` and `099` are different strings that a numeric comparison
# would read as the same course, which is how one course acquires two spellings
# and two rows."
#
# Read out of the spec, not out of any validator: a table copied from the
# implementation would agree with it whatever it says (`docs/MISTAKES.md` entry
# 19). Every value here is an edge or one step past one, and each valid number
# sits beside an invalid one so that neither half of the rule can pass by being
# absent.
NUMBERS_INSIDE_THE_BANDS = (
    "000",  # the first developmental number
    "099",  # the last developmental number
    "100",  # the first undergraduate number
    "499",  # the last undergraduate number
    "500",  # the first dual-credit number
    "599",  # the last dual-credit number
    "600",  # the first graduate number
    "799",  # the last three-digit number of any kind
    "8000",  # the first doctoral number
    "9999",  # the last doctoral number
)

NUMBERS_OUTSIDE_THE_BANDS = (
    "800",  # one past the three-digit ceiling
    "999",  # the highest three-digit number, and no band holds it
    "0099",  # `099` with a leading zero: four digits, below 1000
    "1000",  # the lowest four-digit number outside the doctoral band
    "7999",  # one below the doctoral floor
    "10000",  # five digits, which no band has a width for
)


def the_one(rows: list[Any], what: str) -> Any:
    """Exactly one row, or a failure that says which of the two failures happened."""
    assert (
        len(rows) == 1
    ), f"There are {len(rows)} rows where there should be exactly one {what}: {rows}."
    return rows[0]


def the_defect(rows: Any, names: Any, claims: Any, kind: str) -> Any:
    """Exactly one `launch_defect` row, of `kind`, naming this launch's own three identifiers.

    The identifiers are asserted against the claims rather than against constants,
    so a writer that recorded a defect for some *other* launch — the last one it
    saw, a default, an empty string — fails here. E11's admin surface reads this
    table to answer "which launches could not be ingested", and a row that names
    the wrong deployment sends somebody to the wrong LMS.
    """
    recorded = the_one(rows.defects(), f"`{names.defect_table}` row of kind {kind!r}")
    written = str(getattr(recorded["kind"], "value", recorded["kind"]))
    assert written == kind, (
        f"The recorded defect's kind is {written!r} and this launch's defect is {kind!r}. A "
        "record that names the wrong rule is worse than no record: it is a wrong answer to the "
        "one question E11's surface exists to ask, and it reads as though somebody checked."
    )
    assert recorded["issuer"] == claims.get("iss"), (
        f"The defect names issuer {recorded['issuer']!r} and the launch came from "
        f"{claims.get('iss')!r}."
    )
    assert recorded["deployment_id"] == claims.get(names.deployment_id_claim), (
        f"The defect names deployment {recorded['deployment_id']!r} and the launch carried "
        f"{claims.get(names.deployment_id_claim)!r}."
    )
    assert recorded["context_id"] == names.context_id_of(claims), (
        f"The defect names context {recorded['context_id']!r} and the launch's context claim "
        f"carries id {names.context_id_of(claims)!r}. The context id is the only handle E11 has "
        "on which course could not be read."
    )
    return recorded


def assert_nothing_was_written(rows: Any, what: str) -> None:
    """No course and no section anywhere — criterion 5's "nothing is written".

    Both tables, because a defect is atomic across the two: E1-10's work order,
    "a defect anywhere means course AND section are both unwritten". A course
    written for a launch whose section could not be derived is a row nothing will
    ever complete, and it takes the course number with it — so a later, correct
    launch of the same course finds a row it did not write.

    **Scoped to the whole table rather than to a key**, deliberately. The point of
    a refusal is that no row appeared; a check filtered by the key the writer was
    supposed to use would miss a row written under a key it made up.
    """
    assert not rows.courses(), f"{what} wrote the course rows {rows.courses()}."
    assert not rows.sections(), f"{what} wrote the section rows {rows.sections()}."


# ---------------------------------------------------------------------------
# The four defects a real launch can be made to carry.
# ---------------------------------------------------------------------------


def test_a_launch_with_everything_seeded_records_no_defect(
    launch_driver: Any,
    provisioning_contract: Any,
    launch_ground: Any,
    provisioned_rows: Any,
) -> None:
    """The control every test in this module rests on: a complete environment records nothing.

    Each defect below is posed by removing exactly one row from this environment.
    Without this test, "a defect was recorded" would be equally consistent with a
    writer that records one on every launch — and the four cases below would each
    be passing for a reason that has nothing to do with the thing they removed
    (`docs/MISTAKES.md` entry 3).

    It is also where "the record is not noise" is asserted. A `launch_defect` row
    is something a human reads and acts on, so a writer that logged one for every
    successful ingestion would make the surface E11 builds useless without failing
    anything else here.
    """
    offer = launch_driver.offer_for_role(provisioning_contract.instructor_role_urn)
    label = provisioning_contract.label_of(launch_driver.claims_of(offer))
    launch_ground(label)

    response, _ = launch_driver.launch(offer)

    launch_driver.accepted(response, "an instructor's launch into a fully seeded environment")
    assert provisioned_rows.courses(), (
        "The launch wrote no course, so this environment is not the working one the four defect "
        "tests below are each one row away from. "
        "`test_a_staff_launch_creates_the_course_its_context_label_names` is where that is "
        "diagnosed."
    )
    assert not provisioned_rows.defects(), (
        f"A launch that provisioned correctly also recorded {provisioned_rows.defects()}. The "
        "defect table is a surface a human reads and acts on; a row per successful launch makes "
        "it noise, and every assertion below would be satisfied by a writer that records one "
        "every time."
    )


def test_a_context_that_carries_no_label_is_refused_and_recorded(
    launch_driver: Any,
    provisioning_contract: Any,
    launch_ground: Any,
    provisioned_rows: Any,
) -> None:
    """Todd's ruling of 2026-08-26, first half: `id` alone identifies no course.

    E0-14 withdrew this context from the mock's seed and E1-07 minted it back as
    `titleless_context`: a context claim carrying its required `id` and neither a
    `title` nor a `label`. LTI 1.3 permits it, so a real platform may send it, and
    there is nothing in it to resolve a prefix or a course number from — the
    ruling is that such a launch is refused and recorded rather than provisioned
    from a guess.

    **Its pair is next door**: `titleless_context_with_label` keeps the label and
    loses only the title, and that one provisions with the fallback title. Two
    mints and two opposite outcomes, because the difference between them is
    exactly the member E1-10 parses.

    The environment is complete — prefix, term and map row all seeded — so the
    refusal can only be the label.
    """
    offer = launch_driver.offer_for_role(provisioning_contract.instructor_role_urn)
    label = provisioning_contract.label_of(launch_driver.claims_of(offer))
    launch_ground(label)

    response, signed = launch_driver.launch(offer, defect=provisioning_contract.titleless_context)

    launch_driver.accepted(response, "a launch whose context carries neither label nor title")
    context = provisioning_contract.context_of(signed.claims)
    assert "label" not in context, (
        f"The launch this test drove carries a context label ({context.get('label')!r}), so it is "
        "parseable and this test is not about what it says it is about."
    )
    assert_nothing_was_written(provisioned_rows, "A launch whose context claim carries no label")
    the_defect(
        provisioned_rows,
        provisioning_contract,
        signed.claims,
        provisioning_contract.unparseable_context_label,
    )


def test_a_prefix_the_org_does_not_hold_is_refused_and_recorded(
    launch_driver: Any,
    provisioning_contract: Any,
    launch_ground: Any,
    provisioned_rows: Any,
) -> None:
    """A launch may not invent the containment chain it hangs from.

    SPEC §2.1 builds the org top-down — institution, college, department, prefix —
    and a `prefix` is a Pulse-owned node an administrator creates. A launch
    carrying `BIOL` when nothing in the org holds `BIOL` is a configuration gap
    somebody has to see, and ADR 0021 already records the same shape one level
    down: "a cohort whose calendar an admin has not configured is a configuration
    gap someone has to see, and E1 sees it as a refused section rather than as a
    section that reports nothing for a term."

    The term and the start-letter map row are still seeded, so the recorded kind
    distinguishes this from the two cases below rather than being the only kind a
    writer knows.
    """
    offer = launch_driver.offer_for_role(provisioning_contract.instructor_role_urn)
    label = provisioning_contract.label_of(launch_driver.claims_of(offer))
    launch_ground(label, prefix=False)

    response, signed = launch_driver.launch(offer)

    launch_driver.accepted(response, "a launch naming a prefix the org does not hold")
    assert_nothing_was_written(
        provisioned_rows, f"A launch naming the unknown prefix {label.prefix!r}"
    )
    the_defect(
        provisioned_rows,
        provisioning_contract,
        signed.claims,
        provisioning_contract.unknown_prefix,
    )


def test_a_launch_on_a_day_no_terms_dates_contain_is_refused_and_recorded(
    launch_driver: Any,
    provisioning_contract: Any,
    launch_ground: Any,
    provisioned_rows: Any,
) -> None:
    """Todd's ruling of 2026-08-26: the section belongs to the term containing the launch day.

    "A new section belongs to the one term whose dates contain the day of the
    launch. No term contains today, or the code's start position is not in that
    term's start-letter map → refused and recorded, nothing written. A pre-term
    launch refusing is a named limit, recorded in the ADR."

    **A term exists in this environment, and it is the wrong one.** That is the
    whole design of the case: an empty `term` table satisfies both "no term
    contains today" and "there are no terms", so a writer that took the only term
    it could find — or the most recent one — would pass against an empty table and
    put every section of the year into whichever term happened to be there. The
    term seeded here is a year away and carries a start-letter map row for this
    launch's own code, so nothing but the dates can be what refuses it.
    """
    offer = launch_driver.offer_for_role(provisioning_contract.instructor_role_urn)
    label = provisioning_contract.label_of(launch_driver.claims_of(offer))
    launch_ground(label, term="past")

    response, signed = launch_driver.launch(offer)

    launch_driver.accepted(response, "a launch on a day no term's dates contain")
    assert_nothing_was_written(
        provisioned_rows, "A launch on a day outside every term this deployment holds"
    )
    the_defect(
        provisioned_rows,
        provisioning_contract,
        signed.claims,
        provisioning_contract.no_term_for_launch_date,
    )


def test_a_start_position_this_terms_map_does_not_hold_is_refused_and_recorded(
    launch_driver: Any,
    provisioning_contract: Any,
    launch_ground: Any,
    provisioned_rows: Any,
) -> None:
    """ADR 0021's refusal, reaching the record: a code the term's map cannot date.

    "A code whose start position the term's map has no row for, or whose derived
    dates leave the term, is **refused** — the section is not written with a
    partial or invented calendar." ADR 0021 also foresaw where the refusal would
    have to surface: "E1's roster sync therefore has a failure it must surface —
    'this section could not be read' — rather than a row it can quietly store."
    This is that surface, arriving for launch-time ingestion.

    **The map holds a row, for another letter.** An empty map would let a writer
    that skipped the lookup entirely pass, and it would not distinguish this case
    from `no_term_for_launch_date` — SPEC §2.2 makes the map per-term
    admin-configured data, so a start position nobody configured is the real
    shape of this gap.
    """
    offer = launch_driver.offer_for_role(provisioning_contract.instructor_role_urn)
    label = provisioning_contract.label_of(launch_driver.claims_of(offer))
    launch_ground(label, letter=False)

    response, signed = launch_driver.launch(offer)

    launch_driver.accepted(response, "a launch whose code has no row in the term's map")
    assert_nothing_was_written(
        provisioned_rows,
        f"A launch whose code starts at {label.start_letter!r}, which this term's map does not "
        "hold",
    )
    the_defect(
        provisioned_rows,
        provisioning_contract,
        signed.claims,
        provisioning_contract.section_code_underivable,
    )


def test_a_defective_context_still_creates_the_launching_subjects_user_row(
    launch_driver: Any,
    provisioning_contract: Any,
    launch_ground: Any,
    provisioned_rows: Any,
) -> None:
    """The person is authenticated; it is the context that failed.

    E1-10's work order rules it in as many words: a `user` row is written on every
    validated launch, "even when the context is defective — the person is
    authenticated; the context is what failed", and criterion 5's "nothing is
    written" covers course, section and address. The two halves are asserted
    together here rather than in separate tests because it is their combination
    that is the rule: a writer that abandoned everything on the first defect would
    pass `assert_nothing_was_written` and fail this, and a writer that wrote the
    course anyway would pass the user half and fail the other.

    Without a `user` row the person exists nowhere in this system, so their next
    launch — which may be against a perfectly good context — starts from nothing,
    and §4's own key for every response they ever give is missing.

    **This test has a second reason for `accepted` beyond the module-wide one.**
    Even where seeding a landing were otherwise possible, it is not here: from
    E1-13 a landing comes from an assignment or an enrollment, and an enrollment
    hangs off the very `user` row this test watches being written — so seeding one
    would be handing back the answer (`docs/MISTAKES.md` entry 30), and a first
    launch by anybody reaches the calm no-access page by construction.
    """
    offer = launch_driver.offer_for_role(provisioning_contract.instructor_role_urn)
    label = provisioning_contract.label_of(launch_driver.claims_of(offer))
    launch_ground(label, prefix=False)

    response, signed = launch_driver.launch(offer)

    launch_driver.accepted(response, "a launch whose context could not be read")
    subject = signed.claims.get("sub")
    assert subject, "The launch carries no `sub`, so there is no subject for a `user` row to be."
    the_one(
        [row for row in provisioned_rows.users() if row.get("lms_user_id") == subject],
        f"`user` row for the launching subject {subject!r}",
    )
    assert_nothing_was_written(provisioned_rows, "A launch whose context could not be read")


# ---------------------------------------------------------------------------
# Criterion 5 — the course-number bands, on both sides of every edge.
# ---------------------------------------------------------------------------


def test_rewriting_a_launchs_course_number_changes_only_the_labels_middle_part(
    launch_driver: Any, provisioning_contract: Any
) -> None:
    """The control on the machinery every band case below is built out of.

    `with_course_number` takes a real launch's claims and rewrites the middle part
    of its context label. If it also changed the prefix, the band tests would be
    testing `unknown_prefix`; if it changed the code, they would be testing
    `section_code_underivable`; if it changed nothing, the invalid half would be
    asserting a refusal of the mock's own perfectly good number.

    **This test must be green whatever the writer does** — nothing here calls the
    writer at all. A red here means the tests below are broken rather than that
    the code is, and it is the first thing to read when they fail together.
    """
    offer = launch_driver.offer_for_role(provisioning_contract.instructor_role_urn)
    claims = launch_driver.claims_of(offer)
    original = provisioning_contract.label_of(claims)
    assert original.number != "8000", (
        "The mock platform's own course number is already 8000, so the rewrite below changes "
        "nothing and this control cannot tell a working helper from one that does nothing. Pick "
        "another number here."
    )

    rewritten = provisioning_contract.with_course_number(claims, "8000")
    changed = provisioning_contract.label_of(rewritten)

    assert changed.number == "8000", f"The rewritten label is {changed.label!r}."
    assert (changed.prefix, changed.code) == (original.prefix, original.code), (
        f"Rewriting the number turned {original.label!r} into {changed.label!r}, which changes "
        "more than the number. Every band case below would then be posing two defects at once and "
        "unable to say which one fired."
    )
    assert provisioning_contract.label_of(claims).number == original.number, (
        f"Rewriting the number edited the original claims in place: the label is now "
        f"{provisioning_contract.label_of(claims).label!r}. Two parametrised cases would see each "
        "other's number."
    )


@pytest.mark.parametrize("number", NUMBERS_INSIDE_THE_BANDS)
def test_a_course_number_inside_spec_8s_bands_is_provisioned(
    registered_platform: Any,
    provisioning: Any,
    provisioning_contract: Any,
    launch_ground: Any,
    rows_on: Any,
    db_session: Any,
    number: str,
) -> None:
    """The permitted half of criterion 5, at every edge the bands have.

    Refusing too much is this rule's other failure mode and the one no denial test
    can see. `000` and `099` are developmental numbers with a significant leading
    zero — SPEC §8: "a developmental number carries a significant leading zero
    (`MATH 040`) that an integer cannot hold" — and a validator written over
    `int(number)` accepts them while turning them into a different course. `799`
    and `8000` sit on either side of the gap where three-digit numbers stop and
    four-digit ones begin.

    **The row is required to carry the number as sent.** A course stored as `"99"`
    rather than `"099"` is the second spelling SPEC §8 warns about, and the next
    launch of the same course creates a second row for it.
    """
    offer = registered_platform.offer_for_role(provisioning_contract.instructor_role_urn)
    claims = provisioning_contract.with_course_number(registered_platform.claims_of(offer), number)
    label = provisioning_contract.label_of(claims)
    launch_ground(label)
    rows = rows_on(db_session)

    provisioning.call(provisioning.provision, session=db_session, claims=claims)

    course = the_one(rows.courses(), f"course for the in-band number {number!r}")
    assert course[provisioning_contract.course_number_column] == number, (
        f"The course was stored with number {course[provisioning_contract.course_number_column]!r} "
        f"and the launch carried {number!r}. SPEC §8 stores the number as text because the leading "
        "zero is significant: `0099` and `099` are different strings that a numeric comparison "
        "reads as one course, which is how one course acquires two spellings and two rows."
    )
    assert not rows.defects(), (
        f"A course number inside SPEC §8's bands was recorded as a defect: {rows.defects()}. "
        "Under-inclusion here is a launch that can never provision, and the person sees an empty "
        "product with nothing saying why."
    )


@pytest.mark.parametrize("number", NUMBERS_OUTSIDE_THE_BANDS)
def test_a_course_number_outside_spec_8s_bands_is_refused_and_recorded(
    registered_platform: Any,
    provisioning: Any,
    provisioning_contract: Any,
    launch_ground: Any,
    rows_on: Any,
    db_session: Any,
    number: str,
) -> None:
    """Criterion 5: "An out-of-band course number is refused and recorded; nothing is written."

    SPEC §8: "Numbers outside the bands are rejected at write time rather than
    stored with an absent or guessed level. A roster sync carrying an unexpected
    number is a defect to see, not a row to accept."

    **The refusal has to be Python's, before the write.** `course.level` is a
    stored generated column and its `NOT NULL` already refuses an out-of-band
    number (ADR 0015) — but that refusal is a `null value in column "level"`
    error out of Postgres in the middle of a request, which is a 500 and not a
    refusal: the launch fails, the person does not land, and nothing is recorded.
    E1-10's work order states it directly: "Never rely on the generated column's
    NOT NULL to refuse — that is a 500, not a refusal." A writer that leans on the
    constraint fails this test on the defect row that never appears, and the
    in-band cases above are what stop the fix being "reject everything".

    **The edges are the cases.** `800` and `999` are three-digit numbers no band
    holds; `0099` is four digits below `1000`, the case §8 spells out because a
    numeric comparison reads it as `099`; `1000` and `7999` are the four-digit
    range that is not doctoral; `10000` has a width no band has.
    """
    offer = registered_platform.offer_for_role(provisioning_contract.instructor_role_urn)
    claims = provisioning_contract.with_course_number(registered_platform.claims_of(offer), number)
    label = provisioning_contract.label_of(claims)
    launch_ground(label)
    rows = rows_on(db_session)

    provisioning.call(provisioning.provision, session=db_session, claims=claims)

    assert_nothing_was_written(rows, f"A launch carrying the out-of-band number {number!r}")
    the_defect(rows, provisioning_contract, claims, provisioning_contract.out_of_band_course_number)


# ---------------------------------------------------------------------------
# The record itself: what it may hold, and what it may never hold.
# ---------------------------------------------------------------------------


def test_the_defect_kinds_are_exactly_the_nine_these_tickets_enumerate(
    metadata_tables: dict[str, Any], provisioning_contract: Any
) -> None:
    """The closed set, pinned as an equality rather than as a floor.

    `test_the_kind_column_refuses_a_defect_kind_this_ticket_does_not_name` below
    asks the database to accept each kind and to refuse one invented name, and
    that pair cannot see a **further** kind that a later ticket adds: a
    plausible-looking label sits in the type, is accepted, and nothing in this
    suite reports it. E11 builds an administrator's surface on this column and has
    to know what it may be shown, so the set is fixed here and widening it is a
    visible diff in a test — the same shape `RUNTIME_BASE_TABLE_PRIVILEGES` uses
    for the grants and `SANCTIONED_WRITERS_EXPECTED` for the writer catalog.

    **Nine, since E3-02.** Five kinds came from E1-10's own design; that ticket's
    round-3 security review added `context_collision` — a launch naming a section
    another context is bound to, which is the HIGH — and `roster_address_refused`,
    an address the registration rules will not let this container fetch. E2-02 adds
    `context_outside_purview` for the E1 boundary review's M9: a launch admitted by
    §7.3's leadership limb whose context sits outside the launching person's own
    grant, which binds nothing and stores no roster address.

    **E3-02 adds `ags_address_refused`**, and this equality is what made that
    widening a deliberate diff rather than a label nobody noticed — it went red on
    the ninth label and `docs/disputes/E3-02-01.md` is the record. That ticket
    stores the AGS line-item container address a launch advertises, judged by the
    same chokepoint as the roster address, and a refused one leaves
    `section.lms_ags_line_items_url` unset while the launch still succeeds. It is
    the exact mirror of `roster_address_refused` and it is a separate kind for the
    reason E11's surface exists: a refused roster address and a refused gradebook
    address are different services and different conversations with whoever
    configured the platform. A launch carrying no AGS claim at all records nothing,
    because a section with no gradebook is a state and not a fault.

    **Read off the column's own type**, which is where E1-10 settles the set:
    "`kind` (closed string enum of exactly the five kinds above)", now nine. A
    column that is not an enum fails here saying so rather than being read as an
    empty set, because "no labels" and "a free-text column" are the same silence
    and only one of them is a defect this test can describe.
    """
    from sqlalchemy.types import TypeDecorator

    table = metadata_tables.get(provisioning_contract.defect_table)
    assert table is not None, (
        f"There is no `{provisioning_contract.defect_table}` table on `Base.metadata` (it holds "
        f"{sorted(metadata_tables)}). E1-10's migration adds it."
    )
    column = table.columns.get("kind")
    assert column is not None, (
        f"`{provisioning_contract.defect_table}` has no `kind` column (it has "
        f"{[c.name for c in table.columns]}). It is the field E11's surface groups by."
    )
    kind = column.type
    while isinstance(kind, TypeDecorator):
        kind = kind.impl_instance
    labels = tuple(getattr(kind, "enums", ()) or ())
    assert labels, (
        f"`{provisioning_contract.defect_table}.kind` is typed {column.type!r}, which enumerates "
        "nothing. E1-10 makes it a closed enum precisely so the administrator's surface E11 builds "
        "can know what it may be shown; a free-text column has to render whatever string the next "
        "writer invents, and this test cannot tell that apart from an enum with no members."
    )
    assert set(labels) == set(provisioning_contract.defect_kinds), (
        f"`{provisioning_contract.defect_table}.kind` enumerates {sorted(labels)} and E1-10 "
        f"enumerates {sorted(provisioning_contract.defect_kinds)}.\n\n"
        "A kind in the column and not in the record is one an administrator can be shown with "
        "nothing saying what it means; a kind in the record and not in the column is a defect the "
        "writer cannot record at all, which is `docs/MISTAKES.md` entry 26 — the fallback path "
        "losing the failure it exists to surface. If a later ticket genuinely adds one, "
        "`DEFECT_KINDS` in tests/fixtures/provisioning.py is where it is recorded, in the pull "
        "request that adds it."
    )


def test_the_defect_record_carries_exactly_the_fields_this_ticket_enumerates(
    metadata_tables: dict[str, Any], provisioning_contract: Any
) -> None:
    """E1-10's scope enumerates the record's field set, and an equality is what holds it.

    "The record's field set is enumerated in this ticket's design: defect kind,
    issuer, deployment, context id, timestamp — never a claim payload, a name, an
    email, or `lms_user_id` (§10; the stable join key E1-01 keeps out of views does
    not enter an Admin-visible record here either), and log lines on this path
    carry no more than the record does."

    **An equality rather than a subset, and both directions matter.** A column
    added later — `sub`, so an admin can tell who was launching; `claims`, so a
    developer can debug it — is precisely the change this test exists to force a
    conversation about, and no `>=` check would see it. A column *missing* leaves
    E11 unable to answer which deployment a defect came from, which is the whole
    use of the record.

    This is a structural check and the behavioural one is beside it:
    `test_a_recorded_defect_names_nobody` asserts that no value in a real defect
    row is a value from the launching person, which is the half that survives a
    column named something innocuous.
    """
    table = metadata_tables.get(provisioning_contract.defect_table)
    assert table is not None, (
        f"There is no `{provisioning_contract.defect_table}` table on `Base.metadata` (it holds "
        f"{sorted(metadata_tables)}). E1-10's migration adds it: an append-only, Pulse-owned "
        "record of the launches that could not be ingested, which E11 reads later."
    )

    present = {column.name for column in table.columns}
    assert present == set(provisioning_contract.defect_columns), (
        f"`{provisioning_contract.defect_table}` carries {sorted(present)} and E1-10 enumerates "
        f"{sorted(provisioning_contract.defect_columns)}.\n\n"
        "SPEC §10 requires no student personal information in logs, and this record is the "
        "Admin-visible surface E11 builds on. A column beyond the five is a widening of what an "
        "ingestion failure discloses about the person who happened to launch — and the natural "
        "ones to add are the worst: `sub` is the stable join key E1-01 keeps out of every view, "
        "and a claims payload carries the name and the email address outright.\n\n"
        "A missing column is the other failure: without `deployment_id` the record cannot say "
        "which LMS a defect came from, and E11's surface can only report that something went "
        "wrong somewhere."
    )


@pytest.mark.invariant
def test_a_recorded_defect_names_nobody(
    launch_driver: Any,
    provisioning_contract: Any,
    launch_ground: Any,
    provisioned_rows: Any,
) -> None:
    """SPEC §10 over a real record: no value in the row came from the person who launched.

    The structural test above pins the column names; this one pins the values,
    and the two catch different things. A column called `context_id` holding the
    `sub` claim passes the structural check and is exactly the disclosure §10
    forbids — and it is a plausible mistake, because both are opaque identifiers
    the launch carries.

    **The canary is the launch's own claims.** The values searched for are read
    off the launch rather than written down here, and at least one of them has to
    actually be present, or this test would pass against a record that copied the
    whole claims payload of a launch that happened to carry none of them
    (`docs/MISTAKES.md` entry 3).

    **Marked `invariant`, which reverses what this docstring used to say.** It
    said §4.1's invariants are about what a read path discloses to a person
    holding a role, that this is §10's rule about what gets written down, and that
    the pass has a meaning worth keeping narrow. E1's boundary review ruled the
    other way (finding M6, `docs/tickets/e1/boundary-review.md`), and the note is
    corrected here rather than left standing beside a marker that contradicts it
    (`docs/MISTAKES.md` entry 1). Two reasons: the row is the Admin-visible
    surface E11 builds on — the structural test above says so — so a `sub` or a
    name copied into it *is* disclosed to a person holding a role, by a slower
    route than a view; and the pass exists so that a confidentiality denial cannot
    be skipped, deleted or emptied without CI saying so, which is a property this
    test wants whichever section states the rule it enforces.
    """
    offer = launch_driver.offer_for_role(provisioning_contract.instructor_role_urn)
    label = provisioning_contract.label_of(launch_driver.claims_of(offer))
    launch_ground(label, prefix=False)

    response, signed = launch_driver.launch(offer)

    launch_driver.accepted(response, "a launch whose context could not be read")
    recorded = the_one(provisioned_rows.defects(), "recorded defect")

    personal = {
        name: str(signed.claims[name])
        for name in ("sub", "name", "given_name", "family_name", "email")
        if signed.claims.get(name)
    }
    assert personal, (
        "This launch's claims carry a real value under none of `sub`, `name`, `given_name`, "
        "`family_name` or `email`, so there is nothing for the record to have leaked and the "
        "assertion below is vacuous. The mock platform's launches carry a subject at minimum."
    )

    written = {name: str(value) for name, value in recorded.items() if value is not None}
    leaked = sorted(
        f"{column} holds the launch's {claim} ({value!r})"
        for column, value in written.items()
        for claim, personal_value in personal.items()
        if personal_value in value
    )
    assert not leaked, (
        f"The defect record carries values from the launching person: {leaked}. The whole row is "
        f"{dict(recorded)}.\n\n"
        "SPEC §10: no student personal information in logs. E1-10 enumerates this record's fields "
        "as the defect kind, the issuer, the deployment, the context id and a timestamp — 'never "
        "a claim payload, a name, an email, or `lms_user_id`'. An ingestion failure is a fact "
        "about a course, and the person who happened to be launching at the time is not part of "
        "it."
    )


def test_the_kind_column_refuses_a_defect_kind_this_ticket_does_not_name(
    seed_rows: Any, db_session: Any, provisioning_contract: Any
) -> None:
    """The kinds are a closed set, held by the database rather than by the writer.

    E1-10's design: `kind` is "a closed string enum of exactly the five kinds
    above" — seven since round 3's review added `context_collision` and
    `roster_address_refused`, eight since E2-02 added `context_outside_purview`,
    and nine since E3-02 added `ags_address_refused`. Closed in the schema is what
    makes E11's surface able
    to enumerate what it may be shown; a free-text column means the admin console
    has to cope with whatever string a later ticket invents, and it will not.

    **Both directions in one test**, because a database that refused every insert
    would satisfy the refusal alone and make the whole record unwritable. Every
    kind is required to be accepted, and one this ticket does not name is required
    to be refused, and the refusal is the database's — a check the writer makes in
    Python is undone by the next writer. Which kinds those are is
    `test_the_defect_kinds_are_exactly_the_nine_these_tickets_enumerate` above:
    this test would go on passing if a tenth were added, and that one is what
    would not — as it did not when E3-02 added the ninth.

    The exception type is deliberately not named: a Postgres enum answers with a
    `DataError` and a `CHECK` constraint with an `IntegrityError`, and E1-10
    settles that the set is closed without settling which mechanism closes it.
    """
    from sqlalchemy.exc import DatabaseError

    for kind in provisioning_contract.defect_kinds:
        savepoint = db_session.begin_nested()
        try:
            seed_rows(provisioning_contract.defect_table, {}, kind=kind)
        except DatabaseError as refused:
            savepoint.rollback()
            pytest.fail(
                f"The database refused a `{provisioning_contract.defect_table}` row of kind "
                f"{kind!r} ({refused}). Every one of them is a kind this suite enumerates and a "
                "writer records, so a "
                "refusal here makes the defect unwritable and the fallback path silently loses "
                "the failure it was supposed to surface (`docs/MISTAKES.md` entry 26)."
            )
        savepoint.rollback()

    invented = "a_kind_no_ticket_names"
    savepoint = db_session.begin_nested()
    try:
        seed_rows(provisioning_contract.defect_table, {}, kind=invented)
    except DatabaseError:
        savepoint.rollback()
        return
    savepoint.rollback()
    pytest.fail(
        f"The database accepted a `{provisioning_contract.defect_table}` row whose kind is "
        f"{invented!r}. E1-10 makes `kind` a closed set of exactly "
        f"{sorted(provisioning_contract.defect_kinds)}; open, it is a free-text column, and the "
        "admin surface E11 builds on it has to render whatever string the next writer invents."
    )
