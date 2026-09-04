"""The AGS container address a launch supplies — ticket E3-02, criterion 1.

> A launch carrying an AGS endpoint claim stores the container address on the
> section; a launch carrying a loopback or otherwise refused address records a
> defect and leaves the column unset, with the launch itself still succeeding.
> Both directions asserted.

SPEC §3.4 puts "one AGS line item per section" in the platform's gradebook, and
before anything can be created there the tool has to know *where* — the launch
carries the AGS endpoint claim, whose `lineitems` member names the container for
the launched context. E3-02 stores it on `section` as an exact mirror of the
roster address §7.3 already has a staff launch store, and the mirror is the whole
design: the same chokepoint judges it
(`app.models.lti.refuse_invalid_fetched_address`), the same enumerations list it
(`FETCHED_COLUMNS` and `LOOPBACK_REFUSED_COLUMNS`, pinned in
`tests/unit/test_registration_address_constraints.py`), and a refused address is
recorded as a launch defect rather than turned into a refused launch.

**Three states, and the ticket makes them three rather than two.** A section whose
platform advertised an address this tool will call; a section whose platform
advertised one it will not; and a section whose platform advertised none at all.
Only the second is a fault. The third is the state §7.3 already draws for the
roster — "a section with no roster and a section with no enrollments are different
states and only one of them is a fault" — and the ticket says the same of the
gradebook in as many words: "A platform that supplies no AGS claim is a section
with no gradebook, which is a state to record and not a fault to raise." So the
absent-claim case here asserts **no defect at all**, which is what separates it
from the refusal beside it.

**Where each half is driven, and why the two are not one.** The ordinary path runs
through the whole door, in development, against the address the in-repo platform
really sends: a writer that built the container URL out of the issuer and a
guessed path would pass a test that handed it a claims dictionary, and there is no
substitute for reading what the platform signed. The refusals run at the writer,
under a deployment's `ENVIRONMENT`, because every rule the chokepoint applies is
switched off under the development name — a refusal test in development asserts
nothing at all — and because no mint produces a launch advertising the cloud
metadata service. That split is `test_a_roster_address_is_judged_by_the_
registration_rules.py`'s, and this module borrows it whole rather than inventing a
second arrangement (`docs/MISTAKES.md` entry 13).

**Every vector below is an IP literal or a value the spelling rules refuse before
anything is looked up.** `provision_from_launch` passes no resolver, so under a
deployment it resolves with the machine's own name server, and a hostname here
would make this module's result depend on what DNS answered (`docs/MISTAKES.md`
entry 40's shape arriving through a resolver). A literal is judged without a
query.

**The refused rows carry an acceptable *roster* address, and the accepted rows
carry one too.** Two addresses on one launch travel the same chokepoint, so a
launch left carrying the mock's own cleartext roster address would record a
`roster_address_refused` defect under a deployment's name and every assertion here
about "the defect" would be about the wrong one (`docs/MISTAKES.md` entry 3). The
roster address is also *asserted stored* in the refusal test, which is what says
the writer ran at all and that only the gradebook half was refused.

**The defect kind is discovered, not named.** The ticket asks for "a new
`LaunchDefectKind` member, mirror `roster_address_refused`" and spells no name, so
naming one here would settle an interface the ticket leaves open on the
implementer's behalf. `the_kind_this_ticket_adds` reads the enum and subtracts the
kinds that already existed; one new member is the answer, two is an interface
question for the pull request, and none is the ticket not built yet. The control
at the foot of this module is what makes that subtraction well-founded.

**Which failure a red here is.** Before E3-02 lands, every test in the two
criterion-1 sections is expected red on a failed assertion naming
`section.lms_ags_line_items_url` as a column the row does not carry, or naming the
absent defect kind — not on a collection error. The two controls at the end must be
green today: they are statements about the launch the in-repo platform signs and
about the defect vocabulary that already exists, and a red one means these tests
are broken rather than that the code is.
"""

from typing import Any

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.lti]

# `launch_driver`, `launch_driver_in`, `launch_ground`, `provisioned_rows`,
# `provisioning_contract`, `provisioning`, `registered_platform` and `rows_on` all
# come from `tests/fixtures/provisioning.py` and are reached as fixtures rather
# than imported: an import of a fixtures module by name depends on where pytest
# put `tests/` on `sys.path`, and an import error is not a red.

# A deployment's `ENVIRONMENT`. Every rule the chokepoint applies is conditioned on
# not being the development name, so this is the name under which the refusals
# below have a subject at all.
PRODUCTION = "production"

# A real institution's LMS host, for the one vector whose subject is the transport.
DEPLOYED_HOST = "lms.example.edu"

# The gradebook addresses the chokepoint refuses on a column this container
# fetches. Every row carries `https` except the one whose whole subject is the
# transport, so that exactly one rule can be what refuses each of them
# (`docs/MISTAKES.md` entry 3). The values are
# `tests/unit/test_registration_address_constraints.py`'s own, so the two modules
# can be read side by side.
#
# **The two loopback rows are why criterion 2 is a criterion.** Loopback is refused
# only on a column in `LOOPBACK_REFUSED_COLUMNS` — a key-set sidecar on
# `127.0.0.1` is an ordinary deployment and stays legal on `jwks_url` — so these
# two rows are refused if and only if the new column is in that tuple, and they are
# the behaviour behind the enumeration pin next door. Both spellings, because a
# rule written over the IPv4 block alone leaves the IPv6 half.
REFUSED_ADDRESSES = {
    "the cloud metadata service": "https://169.254.169.254/lineitems",
    "another address in the link-local range": "https://169.254.0.1/lineitems",
    "the loopback address": "https://127.0.0.1/lti/lineitems",
    "the IPv6 loopback literal": "https://[::1]/lti/lineitems",
    "cleartext to another host": f"http://{DEPLOYED_HOST}/lti/lineitems",
    "an RFC 1918 address": "https://10.0.0.5/lti/lineitems",
    "an IPv6 unique local address": "https://[fd00::5]/lti/lineitems",
}

# The other direction, and the half the whole rule stands or falls on: a container
# address a real platform advertises and this tool must go on storing. Both are IP
# literals, and that is forced rather than chosen — see the module docstring.
# Neither is in a documentation range: `203.0.113.0/24` and `192.0.2.0/24` read
# like public addresses and report `is_global` false, so either would be refused
# and this pair would assert nothing.
ACCEPTED_ADDRESSES = {
    "a globally routable address": "https://93.184.216.34/lti/lineitems",
    "a globally routable IPv6 address": "https://[2606:4700:4700::1111]/lti/lineitems",
}

# The roster address every launch below carries, so that the gradebook address is
# the only thing a defect here can be about. The mirror of what
# `test_a_roster_address_is_judged_by_the_registration_rules.py` now does for the
# gradebook address in its own fixture.
AN_ACCEPTED_ROSTER_ADDRESS = "https://93.184.216.34/lti/memberships"


def the_one(rows: list[Any], what: str) -> Any:
    """Exactly one row, or a failure saying which of the two failures happened."""
    assert (
        len(rows) == 1
    ), f"There are {len(rows)} rows where there should be exactly one {what}: {rows}."
    return rows[0]


def stored_on(section: Any, column: str, ticket_says: str) -> Any:
    """One column of a `section` row, or a failure naming the column E3-02 adds.

    A `row[column]` on a mapping that has no such key raises `KeyError` from inside
    the assertion, which reads as a broken test rather than as a missing
    deliverable. This is the module's idiom for the same reason
    `tests/fixtures/provisioning.py` discovers the writer rather than naming it:
    what comes out on the current tree is a failed assertion naming what the ticket
    is asked to add.
    """
    if column not in section:
        pytest.fail(
            f"`section` carries no `{column}` column — it carries {sorted(section.keys())}. "
            f"{ticket_says}"
        )
    return section[column]


def the_kind_this_ticket_adds(contract: Any) -> str:
    """The one `LaunchDefectKind` member E3-02 adds, found by subtraction.

    The ticket asks for a new kind mirroring `roster_address_refused` and spells no
    name for it, so this reads the enum and takes away the kinds that already
    existed rather than pinning a spelling. Ambiguity stops rather than picks —
    two new members mean this cannot tell which one the ticket is about, and
    choosing would be the test deciding — which is the contract
    `ProvisioningService.provision` keeps for the same reason.
    """
    try:
        from app.models.lti import LaunchDefectKind
    except ImportError as absent:
        pytest.fail(
            f"`app.models.lti` exposes no `LaunchDefectKind` ({absent}). E1-10 put the closed set "
            "of launch defect kinds there and E3-02 adds one member to it, so without the enum "
            "there is nothing for this module to read."
        )
    declared = {str(getattr(member, "value", member)) for member in LaunchDefectKind}
    known = set(contract.defect_kinds)
    added = sorted(declared - known)
    if len(added) != 1:
        pytest.fail(
            f"`LaunchDefectKind` declares {sorted(declared)}; the kinds that existed before E3-02 "
            f"are {sorted(known)}; the difference is {added}. E3-02 adds exactly one member — a "
            "refused AGS container address, the mirror of `roster_address_refused` — and this "
            "module reads it by subtraction rather than by name so that the spelling stays the "
            "ticket's choice. None means the kind is not there yet. More than one means this "
            "cannot tell which is which: say in the pull request which member is the gradebook "
            "address's, and `the_kind_this_ticket_adds` in this file is the one place that changes."
        )
    return added[0]


def kind_of(defect: Any) -> str:
    """One recorded defect's kind, as a string, whether it comes back as an enum or not."""
    return str(getattr(defect["kind"], "value", defect["kind"]))


def provision(provisioning: Any, session: Any, claims: Any) -> BaseException | None:
    """Run the writer over one launch's claims, answering an escaped exception.

    Answering rather than raising, so the forbidden state — the address is not
    stored — is asserted whichever way the refusal is expressed, and so a refusal
    that escaped is reported as itself rather than as a missing row. Borrowed from
    the roster module, whose own docstring gives the argument.
    """
    try:
        provisioning.call(provisioning.provision, session=session, claims=claims)
    except Exception as escaped:
        return escaped
    return None


@pytest.fixture
def deployed_launch(
    launch_driver_in: Any,
    provisioning_contract: Any,
    launch_ground: Any,
    rows_on: Any,
    db_session: Any,
) -> dict[str, Any]:
    """A registered platform, a seeded environment and a real staff launch, under production.

    The application is built with `ENVIRONMENT` set to a deployment's name, which is
    what puts the registration-address rules in force at all — under the development
    name they accept everything, deliberately, and every refusal below would be
    asserting nothing. Building the tool through `tool_doors` is how the variable is
    set, so a module that reads `Settings` at import is built under it and one that
    reads it per call sees it too (`docs/MISTAKES.md` entry 40).

    The roster address is rewritten to one the rules accept, so the gradebook
    address is the only thing any defect below can be about.
    """
    driver = launch_driver_in(PRODUCTION)
    offer = driver.offer_for_role(provisioning_contract.instructor_role_urn)
    claims = provisioning_contract.with_memberships_url(
        driver.claims_of(offer), AN_ACCEPTED_ROSTER_ADDRESS
    )
    launch_ground(provisioning_contract.label_of(claims))
    return {"claims": claims, "rows": rows_on(db_session), "session": db_session}


# ---------------------------------------------------------------------------
# Criterion 1, the storing half: the address arrives as a claim and is kept.
# ---------------------------------------------------------------------------


def test_a_staff_launch_stores_the_ags_line_items_address_from_its_own_claim(
    launch_driver: Any,
    provisioning_contract: Any,
    launch_ground: Any,
    provisioned_rows: Any,
) -> None:
    """The ordinary path, through the whole door, against the address the platform sent.

    SPEC §3.4 gives every section one line item called "Pulse Participation",
    created by the tool on first launch. A line item is created *in a container*,
    and the AGS endpoint claim's `lineitems` member is the only thing that says
    where that container is — so a section without it is a section E3-04 has
    nowhere to post to, whatever else is true of it.

    **Asserted against the launch's own claim**, so a writer that composed the
    container URL out of the issuer and a guessed path fails: the value has to have
    been read from the token. Nothing here calls AGS; E3-04 is what does, and this
    ticket's scope says so.

    **The mutation this kills:** storing nothing, which is the state at HEAD; and
    storing the roster address in the gradebook column, which every test about a
    refusal would still pass. **Its pair** is the absent-claim test below, where the
    same column is required to stay unset — without it, "the address was stored"
    would be equally true of a writer that put something there unconditionally.

    Driven in development, where the rules accept the mock's own cleartext
    container address; the deployment-name half of the same question is the
    accepted-address test further down.
    """
    offer = launch_driver.offer_for_role(provisioning_contract.instructor_role_urn)
    label = provisioning_contract.label_of(launch_driver.claims_of(offer))
    launch_ground(label)

    response, signed = launch_driver.launch(offer)

    launch_driver.accepted(response, "an instructor's launch")
    advertised = provisioning_contract.line_items_url_in(signed.claims)
    sections = [
        row
        for row in provisioned_rows.sections()
        if row.get(provisioning_contract.section_code_column) == label.code
    ]
    section = the_one(sections, f"section coded {label.code!r}")
    stored = stored_on(
        section,
        provisioning_contract.section_ags_address_column,
        "E3-02 adds it as a nullable text column holding the AGS line-item container the launch "
        "advertised, an exact mirror of `lms_context_memberships_url`.",
    )
    assert stored == advertised, (
        f"The section's `{provisioning_contract.section_ags_address_column}` is {stored!r} and the "
        f"launch advertised {advertised!r} under `{provisioning_contract.ags_claim}`. SPEC §3.4 "
        "creates one line item per section, and a section addressed at somebody else's container "
        "is a participation score posted into another course's gradebook."
    )


def test_a_staff_launch_stores_no_line_item_id_of_its_own(
    launch_driver: Any,
    provisioning_contract: Any,
    launch_ground: Any,
    provisioned_rows: Any,
) -> None:
    """The second column E3-02 adds exists and this ticket does not fill it.

    `ags_line_item_url` is where the created line item's own id lives, so that
    every later post can address it without re-reading a container. **E3-05 is its
    writer** and E3-02 only adds the column — the ticket's out-of-scope list says
    so — and this is what makes that boundary observable rather than a sentence in
    a document.

    **The mutation this kills:** the two columns conflated, either by writing the
    container address into both or by treating one as the other. That would leave
    E3-05 with a column that already looks written and E3-04 posting scores to a
    container rather than to a line item, and every other test in this module would
    stay green.

    A red on the column's absence is the same red the test above gives, which is
    the point of asserting it separately: `section` must carry *both* columns after
    this ticket.
    """
    offer = launch_driver.offer_for_role(provisioning_contract.instructor_role_urn)
    label = provisioning_contract.label_of(launch_driver.claims_of(offer))
    launch_ground(label)

    response, _ = launch_driver.launch(offer)

    launch_driver.accepted(response, "an instructor's launch")
    sections = [
        row
        for row in provisioned_rows.sections()
        if row.get(provisioning_contract.section_code_column) == label.code
    ]
    section = the_one(sections, f"section coded {label.code!r}")
    stored = stored_on(
        section,
        provisioning_contract.section_line_item_column,
        "E3-02 adds it as a nullable text column for the id of the line item this tool creates, "
        "and E3-05 is what writes it.",
    )
    assert stored is None, (
        f"The section carries `{provisioning_contract.section_line_item_column}` = {stored!r} "
        "after a launch. No line item has been created — E3-04 is what calls AGS and E3-05 is what "
        "records the id it returns — so anything in this column now is the container address "
        "wearing the line item's name, and E3-05 would find its work apparently already done."
    )


@pytest.mark.parametrize("spelling", sorted(ACCEPTED_ADDRESSES))
def test_a_gradebook_address_the_registration_rules_allow_is_stored(
    deployed_launch: dict[str, Any],
    provisioning_contract: Any,
    provisioning: Any,
    spelling: str,
) -> None:
    """The near miss, under the same deployment name that refuses the rows below.

    Two addresses a real platform advertises: a globally routable IPv4 address and
    a globally routable IPv6 one. Without this half, every refusal below is
    satisfied by a writer that stores nothing at all — which is exactly the state
    at HEAD, and exactly the implementation a reviewer could not tell from the
    right one.

    The IPv6 row is not decoration: a rule written over the IPv4 classes alone
    either refuses every address it cannot classify or accepts every one, and this
    row is the only thing here that says which.

    **The mutation this kills**: any refusal wider than the chokepoint's — a scheme
    allow-list, a rule that refuses every IP literal, a rule that refuses whatever
    it had to resolve. Each of those passes every refusal below and silently leaves
    real institutions' sections with no gradebook address, which is a state nothing
    raises about.

    Nothing is recorded on this path either: a defect per successful launch would
    make E11's surface noise.
    """
    address = ACCEPTED_ADDRESSES[spelling]
    rows = deployed_launch["rows"]
    claims = provisioning_contract.with_line_items_url(deployed_launch["claims"], address)

    escaped = provision(provisioning, deployed_launch["session"], claims)

    assert escaped is None, f"Provisioning a launch advertising {address!r} raised {escaped!r}."
    section = the_one(rows.sections(), "section")
    stored = stored_on(
        section,
        provisioning_contract.section_ags_address_column,
        "E3-02 adds it, judged by `app.models.lti.refuse_invalid_fetched_address` under a column "
        "constant of its own.",
    )
    assert stored == address, (
        f"The section carries {stored!r} and its platform advertised {address!r}, which the "
        "registration-address rules accept. Refusing it leaves a real institution's section with "
        "no gradebook address and no score ever posted, and no test of the refusals below would "
        "notice."
    )
    assert not rows.defects(), (
        f"A launch advertising an acceptable gradebook address recorded {rows.defects()}. The "
        "defect table is a surface a human reads and acts on."
    )


# ---------------------------------------------------------------------------
# Criterion 1, the refusing half: a defect, an unset column, and a launch that
# still succeeds.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("spelling", sorted(REFUSED_ADDRESSES))
def test_a_gradebook_address_the_registration_rules_refuse_is_not_stored(
    deployed_launch: dict[str, Any],
    provisioning_contract: Any,
    provisioning: Any,
    spelling: str,
) -> None:
    """An address this container will fetch is judged before it is kept.

    The link-local rows are the finding this rule exists for. `169.254.169.254`
    answers instance credentials to anything inside the container that asks, and
    E3-04 will fetch this column with the tool's own client assertion, on a
    schedule, with nobody present — so an address stored here is an unauthenticated
    request the tool makes on somebody else's behalf from inside the network
    boundary. The loopback rows are criterion 2's behaviour: they are refused if
    and only if the new column is in `LOOPBACK_REFUSED_COLUMNS`. The cleartext row
    is a different rule reaching the same column, and the private rows are the
    resolved-address rule that E1's cleanup batch added.

    **Four things are asserted, and the third and fourth are the ticket's ruling.**
    The column is unset — not the platform's value, not a repaired one. A defect is
    recorded, carrying the kind E3-02 adds rather than any kind that existed
    before. The section is still provisioned and its *roster* address is still
    stored, which is what says the writer ran and that only the gradebook half was
    refused. And nothing escaped: a launch may not fail over a URL, because
    refusing it outright would take a real course out of the product.

    **The mutation this kills**: an `isinstance(str)` check, which is what the
    roster column carried until a security review found it; a second copy of the
    rules written beside the chokepoint rather than routed through it
    (`docs/MISTAKES.md` entry 13); and a refusal that raises, which would turn a
    bad claim into a failed launch.

    **Its pair** is the acceptance above, under this same environment name.
    """
    address = REFUSED_ADDRESSES[spelling]
    rows = deployed_launch["rows"]
    claims = provisioning_contract.with_line_items_url(deployed_launch["claims"], address)

    escaped = provision(provisioning, deployed_launch["session"], claims)

    section = the_one(rows.sections(), "section")
    stored = stored_on(
        section,
        provisioning_contract.section_ags_address_column,
        "E3-02 adds it, and a refused address leaves it unset rather than absent from the schema.",
    )
    assert stored is None, (
        f"The section carries `{provisioning_contract.section_ags_address_column}` = {stored!r} "
        f"after a launch advertising {address!r}, which the registration-address rules refuse on "
        "every address this container fetches. E3-04 calls this column with the tool's own "
        "credentials, so a stored value is a request the tool makes to wherever the claim said."
    )
    assert section[provisioning_contract.section_address_column] == AN_ACCEPTED_ROSTER_ADDRESS, (
        "The section's roster address is "
        f"{section[provisioning_contract.section_address_column]!r} rather than "
        f"{AN_ACCEPTED_ROSTER_ADDRESS!r}. The launch carried an acceptable one, so the writer "
        "either did not run or refused more than the gradebook address — and the assertion above "
        "would then be green because nothing was written at all."
    )
    recorded = the_one(rows.defects(), "recorded defect")
    assert kind_of(recorded) == the_kind_this_ticket_adds(provisioning_contract), (
        f"The recorded defect's kind is {kind_of(recorded)!r} and the kind E3-02 adds is "
        f"{the_kind_this_ticket_adds(provisioning_contract)!r}. E11's surface reads this to tell "
        "an administrator that a section has no gradebook address *because its platform "
        "advertised one we will not call*, which is a different conversation from a section whose "
        "platform advertised none — and from a refused roster address, which is a different "
        "service entirely."
    )
    assert escaped is None, (
        "The address was not stored, which is this test's subject and holds — but the refusal "
        f"escaped as {escaped!r}. A section with no gradebook is a state and not a fault, so a "
        "launch may not fail over one."
    )


# ---------------------------------------------------------------------------
# The third state: no claim at all, which is a state and not a fault.
# ---------------------------------------------------------------------------


def test_a_staff_launch_carrying_no_ags_claim_stores_nothing_and_records_no_defect(
    deployed_launch: dict[str, Any],
    provisioning_contract: Any,
    provisioning: Any,
) -> None:
    """The ticket's ruling: no gradebook is a state to record, not a fault to raise.

    A platform that grants this tool no gradebook scope sends no AGS endpoint claim
    at all. That is an institution's configuration rather than a mistake, and the
    section is provisioned exactly as any other is — the ticket: "A platform that
    supplies no AGS claim is a section with no gradebook, which is a state to
    record and not a fault to raise." SPEC §7.3 draws the same line for the roster,
    and §6.3's admin console is where the state is read.

    **This is the pair that makes the refusal above mean something.** Both leave
    the column unset, and only one of them records a defect; a writer that recorded
    a defect whenever the column ended up unset would pass every refusal row and
    fill E11's surface with a line for every section in an institution that never
    granted the scope. Asserting the *absence* of a defect is the only thing that
    separates the two.

    **The mutation this kills**: treating an absent claim as a refused address. And
    the near miss on the other side — treating a refused address as an absent claim
    — is killed by the refusal test, which requires the defect.

    The section is required to exist, so "nothing was stored" cannot be true
    because nothing was provisioned.
    """
    rows = deployed_launch["rows"]
    claims = provisioning_contract.without_ags_claim(deployed_launch["claims"])

    escaped = provision(provisioning, deployed_launch["session"], claims)

    assert escaped is None, (
        f"Provisioning a launch that carries no `{provisioning_contract.ags_claim}` raised "
        f"{escaped!r}. A platform that grants no gradebook scope sends no such claim, which is a "
        "configuration and not an error, and the launch has a person waiting on it."
    )
    section = the_one(rows.sections(), "section")
    stored = stored_on(
        section,
        provisioning_contract.section_ags_address_column,
        "E3-02 adds it, and NULL is what a section with no gradebook address looks like.",
    )
    assert stored is None, (
        f"The section carries `{provisioning_contract.section_ags_address_column}` = {stored!r} "
        "after a launch advertising no AGS endpoint at all. There was nothing to store, so a "
        "value here was composed rather than read — and a composed gradebook address is a score "
        "posted wherever the composition guessed."
    )
    assert not rows.defects(), (
        f"A launch carrying no AGS claim recorded {rows.defects()}. A section with no gradebook "
        "address is a state, in the same spirit as §7.3's never-synced section; the defect table "
        "is a list of things a human is asked to act on, and there is nothing to do about a "
        "platform that grants no gradebook scope."
    )


# ---------------------------------------------------------------------------
# Controls. **A red here means these tests are broken, not the code.**
# ---------------------------------------------------------------------------


def test_the_launch_this_module_drives_advertises_both_service_addresses(
    registered_platform: Any, provisioning_contract: Any
) -> None:
    """A control: the platform really sends a gradebook address, so there is one to store.

    Every assertion above is about what a writer does with the AGS endpoint claim.
    If the launch carried no such claim, the storing test would be about an absence
    and the absent-claim test would be about a launch indistinguishable from every
    other one — two green tests measuring nothing (`docs/MISTAKES.md` entry 3).

    Both members are read, because the module's whole design is that the two
    addresses travel together and are judged apart: the refusal test asserts the
    roster address survived a refused gradebook address, which is a statement about
    a launch that carries both.

    E0-15 built the platform's half of this and
    `tests/integration/test_mock_lms_ags_line_items_and_scores.py` is where its
    absence is diagnosed. Green today.
    """
    claims = registered_platform.claims_of(registered_platform.offers()[0])

    line_items = provisioning_contract.line_items_url_in(claims)
    memberships = provisioning_contract.memberships_url_in(claims)

    assert line_items != memberships, (
        f"The launch advertises {line_items!r} for its line items and {memberships!r} for its "
        "roster, and they are the same string. Then a writer that stored the roster address in "
        "the gradebook column would pass the storing test above, and this module could not tell "
        "the two services apart at all."
    )


def test_every_defect_kind_this_module_subtracts_is_one_the_model_declares(
    provisioning_contract: Any,
) -> None:
    """A control: the subtraction that finds E3-02's new kind starts from the right set.

    `the_kind_this_ticket_adds` reads `LaunchDefectKind` and takes away the kinds
    that existed before this ticket, which are the ones
    `tests/fixtures/provisioning.py` enumerates. If that enumeration named a kind
    the model does not declare — a rename, a typo, a kind removed — the subtraction
    would leave a member that is not new at all, and the refusal test would then
    demand the wrong kind or accept an old one. This is `docs/MISTAKES.md` entry
    35's rule applied to a subtraction: require each name to be *found*, on a
    subject that certainly has it, rather than merely not found.

    Green today, and it stays green after E3-02: the ticket adds a member and
    removes none.
    """
    try:
        from app.models.lti import LaunchDefectKind
    except ImportError as absent:
        pytest.fail(
            f"`app.models.lti` exposes no `LaunchDefectKind` ({absent}), so the vocabulary "
            "`tests/fixtures/provisioning.py` enumerates has nothing to be checked against."
        )
    declared = {str(getattr(member, "value", member)) for member in LaunchDefectKind}

    assert declared, "`LaunchDefectKind` declares no members at all."
    unknown = sorted(set(provisioning_contract.defect_kinds) - declared)
    assert not unknown, (
        f"`tests/fixtures/provisioning.py` lists {unknown} as launch defect kinds and "
        f"`LaunchDefectKind` declares {sorted(declared)}. The subtraction this module uses to find "
        "E3-02's new member would then report a kind that already existed as the new one, and the "
        "refusal test would be asserting the wrong vocabulary."
    )
