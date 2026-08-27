"""A section belongs to the context it was discovered from — ticket E1-10, round 3.

The security review's HIGH, stated as the attack it is. Before this fix,
provisioning resolved a section by what its context *label* parsed to — prefix,
number, section code — and nothing scoped that lookup to the platform, the
deployment or the context. A course copy keeps its section code, which is
ordinary Canvas behaviour and needs no privilege at all, so a staff launch from
the copy resolved the *original* section and did two things to it: repointed
`lms_context_memberships_url` at the copy's own NRPS endpoint, and overwrote
`course.lms_title`. The first is the expensive one — E1-11 fetches that address
with the tool's own credentials, so the roster of the original section, names and
email addresses included, is delivered to whoever holds the copy.

**The fix is an identity, and these tests are about the identity.** `section`
gains `lti_deployment_id` and `lms_context_id`, unique together, and provisioning
resolves by that pair **first**. Found: the matched path, exactly as before —
idempotent upsert, title correction, address update. Not found, and a section with
the same parsed identity already exists: `context_collision`, and nothing is
written or updated, the course title included, because the atomic boundary aborts
before any write.

**Every test here is a pair with the matched path**, and the pairing is what makes
the refusals mean the binding rather than mean a writer that stopped working. The
first test drives two launches from the *same* context, changing the title and the
address, and requires both changes to land. The two after it drive the identical
second launch with one thing different — a new context id, or a renamed label —
and require nothing at all to change.

**Driven at the writer rather than through the door**, and the reason is the same
one the band-edge tests give: the mock platform mints one context per launch page
and this file needs two contexts that parse to one identity, which is a
combination no mint produces. The claims are a real launch's, minted by the
registered platform every other test here launches from, with exactly one member
rewritten per case. The door-driven half — that a launch stamps the binding at
all — is
`test_a_staff_launch_stamps_the_section_with_the_context_it_was_discovered_from`
in `tests/integration/test_launch_time_provisioning.py`.
"""

from typing import Any

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.lti]

# The context the second launch claims to be. **Not derived from the first**: a
# copied course gets an identifier of the platform's own choosing, and a value
# this file invents cannot collide with one by accident.
ANOTHER_CONTEXT_ID = "e1-10-a-context-that-copied-the-section-code"

# What the second launch would rewrite if the lookup were still by label alone.
# The address is the finding's payload — E1-11 fetches this with a tool token — and
# `.invalid` is RFC 2606's, so nothing here resolves even if the assertion below
# ever stopped holding.
ANOTHER_ROSTER_ADDRESS = "https://roster-thief.invalid/contexts/copied/memberships"
ANOTHER_TITLE = "A title the copied course carries"

# A section code the first launch's context did not carry, for the rename case.
# Checked against the launch's own code before it is used, so a mock that ever
# emitted this one cannot make the rename a no-op.
A_RENAMED_SECTION_CODE = "Z9FF"


def the_one(rows: list[Any], what: str) -> Any:
    """Exactly one row, or a failure saying which of the two failures happened."""
    assert len(rows) == 1, (
        f"There are {len(rows)} rows where there should be exactly one {what}: {rows}. Zero is "
        "the writer not running or refusing; more than one is a second row for a thing that has "
        "one identity."
    )
    return rows[0]


def provision(provisioning: Any, session: Any, claims: Any) -> BaseException | None:
    """Run the writer over one launch's claims, answering an escaped exception rather than raising.

    Answering, so the assertions this file is about — the row did not change — are
    made either way. E1-10's work order rules that a provisioning refusal "NEVER
    fails the launch or the person's landing", so an exception reaching this far
    is a real outcome to report; it is just not the subject, and reporting it as
    the subject would hide whichever of the two actually failed.
    """
    try:
        provisioning.call(provisioning.provision, session=session, claims=claims)
    except Exception as escaped:
        return escaped
    return None


def the_collision(rows: Any, names: Any, claims: Any) -> Any:
    """Exactly one `launch_defect` row, of kind `context_collision`, about this launch.

    The context id is asserted against the claims of the launch that was
    *refused*, not the section that was protected: the record's five fields are
    facts about a launch that could not be ingested — issuer, deployment, context
    id — so an administrator reading E11's surface is told which launch to go and
    look at. A record naming the victim's context would send them to the one
    section that is fine.
    """
    recorded = the_one(rows.defects(), f"`{names.defect_table}` row for the refused launch")
    written = str(getattr(recorded["kind"], "value", recorded["kind"]))
    assert written == names.context_collision, (
        f"The recorded defect's kind is {written!r} and this launch's is "
        f"{names.context_collision!r}. A collision recorded under another kind sends whoever reads "
        "E11's surface after the wrong thing — and this is the one defect kind that means somebody "
        "else's section was nearly repointed."
    )
    assert recorded["context_id"] == names.context_id_of(claims), (
        f"The defect names context {recorded['context_id']!r} and the launch that was refused "
        f"carried {names.context_id_of(claims)!r}. The record is about the launch that could not "
        "be ingested, so naming the section it collided with would point an administrator at the "
        "one context that is behaving."
    )
    return recorded


def assert_nothing_moved(rows: Any, names: Any, before: dict[str, Any], who: str) -> None:
    """The course and the section are exactly as they were, and there is no second one.

    Row identity rather than a spot check on the address, because the finding is
    two writes and not one: the roster address is repointed *and* the course title
    is overwritten, and a test that only read the address would report the second
    half as fixed while it was not. Comparing the whole mapping also catches the
    third shape — a delete-and-reinsert, which leaves the values right and gives
    the section a new primary key.

    Exactly one of each, so a second section written *beside* the original — which
    is the other thing an unbound writer could do — is a failure here rather than
    something only a count would notice.
    """
    course = the_one(rows.courses(), "course")
    section = the_one(rows.sections(), "section")

    assert dict(section) == before["section"], (
        f"{who} changed the section it collided with.\n"
        f"  before: {before['section']}\n"
        f"  after: {dict(section)}\n"
        f"The `{names.section_address_column}` is the expensive one: SPEC §7.3 has E1-11 call that "
        "address with the tool's own credentials, so a section pointed at somebody else's endpoint "
        "delivers this section's whole roster — names and email addresses — to whoever supplied "
        "it. Nothing about a launch from another context authorizes that; §2.1 makes a section's "
        "identity the platform's, and the round-3 ruling makes it "
        f"`(lti_deployment_id, {names.section_context_id_column})` rather than whatever its label "
        "parses to."
    )
    assert dict(course) == before["course"], (
        f"{who} changed the course.\n  before: {before['course']}\n  after: {dict(course)}\n"
        "The ruling's boundary is atomic and includes the title: 'nothing written or updated "
        "(course title included — the atomic boundary aborts before any write)'. SPEC §2.1 makes "
        "the title LMS-owned, and the LMS that owns *this* course did not send this one."
    )


def snapshot(rows: Any) -> dict[str, Any]:
    """The one course and the one section as they stand, for comparing against later."""
    return {
        "course": dict(the_one(rows.courses(), "course")),
        "section": dict(the_one(rows.sections(), "section")),
    }


def test_a_sections_binding_is_unique_in_the_database_and_not_only_in_the_writer(
    metadata_tables: dict[str, Any], provisioning_contract: Any
) -> None:
    """The binding is a constraint, so a second writer cannot undo what this one holds.

    The three tests below assert what `app.services.provisioning` does, and ADR
    0045's standing objection applies to all of them: "a caller can bypass it by
    not calling it." E1-11's roster sync writes sections too, and the argument
    that a section has one context has to survive a second writer that never reads
    this module. A unique constraint is what makes it survive — the same shape SPEC
    §8 uses for the rest of this schema's identities, and the reason the ruling
    says "unique together" rather than "looked up together".

    **Both columns, and `NOT NULL` on each.** A nullable half is a section with no
    binding, which is a section resolvable by parsed label again — Postgres treats
    two NULLs as distinct, so a unique index over a nullable column constrains
    nothing about the rows that matter. That is the quiet version of this finding
    coming back.

    **The mutation this kills**: the columns added and stamped with no constraint
    behind them, which every behavioural test in this file passes because the
    writer is the only thing writing.
    """
    section = metadata_tables.get("section")
    assert section is not None, (
        f"There is no `section` table on `Base.metadata` (it holds {sorted(metadata_tables)}). "
        "E0-05 creates it and E1-10 gives it the binding this file is about."
    )
    context_column = provisioning_contract.section_context_id_column
    deployment_columns = sorted(
        {
            key.parent.name
            for key in section.foreign_keys
            if key.column.table.name == "lti_deployment"
        }
    )
    assert context_column in section.c, (
        f"`section` has no `{context_column}` column (it has "
        f"{[c.name for c in section.columns]}). It is the platform's own identifier for the "
        "context a section was discovered from, and without it a section has no identity a course "
        "copy cannot reproduce."
    )
    assert len(deployment_columns) == 1, (
        f"`section` has {len(deployment_columns)} foreign keys to `lti_deployment` "
        f"({deployment_columns}); it references "
        f"{sorted({key.column.table.name for key in section.foreign_keys})}. The binding is the "
        "context id scoped to exactly one registration."
    )
    binding = {context_column, deployment_columns[0]}

    nullable = sorted(name for name in binding if section.c[name].nullable)
    assert not nullable, (
        f"The binding columns {nullable} are nullable. Postgres treats two NULLs as distinct, so a "
        "unique constraint over them constrains nothing about the sections that carry no binding — "
        "and a section with no binding is one resolvable by its parsed label again, which is the "
        "finding this ticket is closing."
    )

    unique_sets = [
        {column.name for column in constraint.columns}
        for constraint in section.constraints
        if constraint.__class__.__name__ == "UniqueConstraint"
    ] + [{column.name for column in index.columns} for index in section.indexes if index.unique]
    assert binding in unique_sets, (
        f"Nothing on `section` makes {sorted(binding)} unique — the unique sets it carries are "
        f"{[sorted(one) for one in unique_sets]}. The tests below say the *writer* refuses a "
        "second section for a bound context; this is what says the database does, which is what "
        "ADR 0045's 'a caller can bypass it by not calling it' asks for and what E1-11's sync, "
        "which writes sections and never reads `app.services.provisioning`, will be held to."
    )


@pytest.fixture
def bound_section(
    launch_driver: Any,
    provisioning_contract: Any,
    launch_ground: Any,
    provisioning: Any,
    rows_on: Any,
    db_session: Any,
) -> dict[str, Any]:
    """One provisioned section, bound to the context that discovered it.

    The starting state of all three tests. Built here rather than in each of them
    so that the thing under test is the *second* launch in every case, and so the
    guard that says the first one worked is written once.

    A red in this fixture is not a red about the collision rule: it means the
    ordinary path stopped provisioning, which
    `tests/integration/test_launch_time_provisioning.py` is where to look.
    """
    offer = launch_driver.offer_for_role(provisioning_contract.instructor_role_urn)
    claims = launch_driver.claims_of(offer)
    label = provisioning_contract.label_of(claims)
    launch_ground(label)
    rows = rows_on(db_session)

    escaped = provision(provisioning, db_session, claims)
    assert escaped is None, (
        f"Provisioning the first launch raised {escaped!r}. Everything in this module starts from "
        "one section that exists and is bound; until that works, nothing here is about a collision."
    )
    assert rows.courses() and rows.sections(), (
        "The first launch created no course and no section, so every 'nothing changed' assertion "
        "in this module would be true of an empty database. "
        "`test_a_staff_launch_creates_the_course_its_context_label_names` is where that is "
        "diagnosed."
    )
    return {
        "claims": claims,
        "label": label,
        "rows": rows,
        "session": db_session,
        "address": provisioning_contract.memberships_url_in(claims),
        "title": provisioning_contract.title_of(claims),
        "context_id": provisioning_contract.context_id_of(claims),
    }


def test_a_second_launch_from_the_same_context_applies_its_title_and_its_address(
    bound_section: dict[str, Any], provisioning_contract: Any, provisioning: Any
) -> None:
    """The matched path, and the reason the two refusals below are not "refuse everything".

    Resolving by `(lti_deployment_id, lms_context_id)` finds this section, so this
    is the same launch arriving again from the same place — a platform that has
    renamed the course and moved its roster service. Both changes have to land:
    SPEC §2.1 makes the title LMS-owned, so the owner's new value is the value,
    and §7.3 has a later staff launch update the stored roster address.

    **This is the pair every test in this module rests on.** A writer that refused
    every second launch satisfies both collision tests and breaks the ordinary
    case — a platform that ever renames anything stops being ingestible, silently,
    with the refusal recorded as somebody else's collision.

    **The mutation it kills**: resolving by the binding and then treating a
    *matched* row as a collision too, which is the cheapest way to make the two
    tests below green.
    """
    rows = bound_section["rows"]
    before = snapshot(rows)
    moved = provisioning_contract.with_memberships_url(
        provisioning_contract.with_context_title(bound_section["claims"], ANOTHER_TITLE),
        ANOTHER_ROSTER_ADDRESS,
    )
    assert bound_section["title"] != ANOTHER_TITLE, "The rewritten title is the original title."
    assert bound_section["address"] != ANOTHER_ROSTER_ADDRESS, (
        "The rewritten roster address is the original address, so 'the update landed' would be "
        "true of a writer that did nothing."
    )

    escaped = provision(provisioning, bound_section["session"], moved)

    assert escaped is None, f"Provisioning the same context a second time raised {escaped!r}."
    section = the_one(rows.sections(), "section")
    course = the_one(rows.courses(), "course")
    assert section[rows.key("section")] == before["section"][rows.key("section")], (
        "The second launch from the same context created a different section row rather than "
        "matching the bound one. The binding is `(lti_deployment_id, "
        f"{provisioning_contract.section_context_id_column})` and neither half changed."
    )
    assert section[provisioning_contract.section_address_column] == ANOTHER_ROSTER_ADDRESS, (
        f"The section still points at {section[provisioning_contract.section_address_column]!r} "
        f"after its own platform advertised {ANOTHER_ROSTER_ADDRESS!r}. §7.3 has the address "
        "arrive on a staff launch and be stored; a platform that moves its roster service is the "
        "ordinary reason it changes."
    )
    assert course[provisioning_contract.course_title_column] == ANOTHER_TITLE, (
        f"The course still holds {course[provisioning_contract.course_title_column]!r} after its "
        f"own platform sent {ANOTHER_TITLE!r}. The LMS owns the title."
    )
    assert not rows.defects(), (
        f"A launch from the context this section is bound to recorded {rows.defects()}. The "
        "matched path is the ordinary path and records nothing."
    )


def test_a_launch_from_another_context_carrying_the_same_label_changes_nothing(
    bound_section: dict[str, Any], provisioning_contract: Any, provisioning: Any
) -> None:
    """The HIGH, driven: a copied course may not repoint the original's roster address.

    The second launch differs from the first in exactly one member the platform
    controls — the context claim's `id` — and in the two values it would rewrite
    if the lookup were still by parsed label: the title and the NRPS address.
    Everything a label parses to is identical, because that is what a course copy
    is: Canvas keeps the section code, and no privilege is needed to make one.

    **What is asserted is the forbidden state**, over the whole of both rows: the
    section is byte-for-byte what it was, the course is what it was, and there is
    exactly one of each. The address is the expensive half — E1-11 calls it with
    the tool's own credentials, so a repointed section hands its roster, names and
    email addresses included, to whoever supplied the endpoint — and the title is
    the half a narrower test would have missed.

    **The mutation this kills**: resolving a section by `(course, term,
    lms_section_code)`, which is what the code did before this round and which
    every other test in this ticket's suite was green against. It also kills the
    half-fix — adding the binding columns and stamping them while still resolving
    by the parsed identity — because the row would be found and updated exactly as
    before.

    **Its pair is the test above**, where the identical second launch from the
    *bound* context applies both changes. Without it, every assertion here is
    satisfied by a writer that ignores second launches.
    """
    rows = bound_section["rows"]
    before = snapshot(rows)
    copied = provisioning_contract.with_memberships_url(
        provisioning_contract.with_context_title(
            provisioning_contract.with_context_id(bound_section["claims"], ANOTHER_CONTEXT_ID),
            ANOTHER_TITLE,
        ),
        ANOTHER_ROSTER_ADDRESS,
    )
    assert bound_section["context_id"] != ANOTHER_CONTEXT_ID, (
        "The second launch carries the same context id as the first, so it is the bound context "
        "and this test is not about a collision at all."
    )
    assert provisioning_contract.label_of(copied).label == bound_section["label"].label, (
        f"The copied launch's label is {provisioning_contract.label_of(copied).label!r} and the "
        f"original's is {bound_section['label'].label!r}. The whole case is one label from two "
        "contexts; with different labels there is nothing to collide."
    )

    escaped = provision(provisioning, bound_section["session"], copied)

    assert_nothing_moved(
        rows, provisioning_contract, before, "A launch from a context carrying the same label"
    )
    the_collision(rows, provisioning_contract, copied)
    assert escaped is None, (
        f"Nothing was changed, which is this test's subject and holds — but the refusal escaped "
        f"as {escaped!r} rather than being recorded. E1-10's work order: a provisioning refusal "
        "never fails the launch or the person's landing, and the record IS the visibility "
        "(`docs/MISTAKES.md` entry 26)."
    )


def test_a_renamed_context_is_recorded_rather_than_becoming_a_second_section(
    bound_section: dict[str, Any], provisioning_contract: Any, provisioning: Any
) -> None:
    """ADR 0091's named residue, arriving as a recorded defect instead of a silent row.

    The other direction of the same identity: one context, a label that has
    changed. ADR 0091 recorded this as residue — "a renamed label is a new
    section" — and the round-3 ruling closes it, because the binding is unique: a
    launch that would write a second section for a context already bound is
    refused and recorded as `context_collision` rather than quietly splitting one
    section's term in two.

    Only the section code changes, so the course this launch names is the course
    the section already sits under and nothing else about the launch has moved.

    **The mutation this kills**: keeping the binding columns and letting a
    renamed label write a second row, which is what the pre-round-3 code did and
    which nothing in this suite would otherwise notice — the old section keeps its
    responses and the new one collects the next term's, and only somebody counting
    sections would ever see it.

    **Its pair is the matched-path test above**: a second launch from this context
    that has *not* been renamed is applied rather than refused.
    """
    rows = bound_section["rows"]
    before = snapshot(rows)
    assert bound_section["label"].code != A_RENAMED_SECTION_CODE, (
        f"The rename uses {A_RENAMED_SECTION_CODE!r}, which is the code this context already "
        "carries, so nothing is renamed and this test is the idempotence test under another name."
    )
    renamed = provisioning_contract.with_section_code(
        bound_section["claims"], A_RENAMED_SECTION_CODE
    )

    escaped = provision(provisioning, bound_section["session"], renamed)

    assert_nothing_moved(rows, provisioning_contract, before, "A launch whose context was renamed")
    the_collision(rows, provisioning_contract, renamed)
    assert escaped is None, (
        f"Nothing was written, which is this test's subject and holds — but the refusal escaped "
        f"as {escaped!r} rather than being recorded. ADR 0091 carried this case as residue "
        "precisely because it was invisible; a refusal nobody records leaves it invisible."
    )
