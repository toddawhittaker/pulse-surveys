"""An address out of a claim is judged like an address out of a registration — E1-10, round 3.

The security review's MEDIUM. `lms_context_memberships_url` is stored from the
NRPS claim on a launch, and it is the third address in this system that this
container fetches: E1-11 calls it with the tool's own client credentials, on a
schedule, without a person present. E1-05 fixed a floor for the other two —
`jwks_url` and `auth_token_url` — at one chokepoint,
`app.models.lti.refuse_invalid_registration_addresses`, whose fourth rule exists
for exactly one address: "the cloud metadata service lives at `169.254.169.254`
and no legitimate LMS does". Before this round the roster address reached the
column on a bare "is it a string" check, so a launch could name that host and
E1-11 would fetch it with a token.

**One helper, not a second copy of the rules** (`docs/MISTAKES.md` entry 13). The
ruling routes the claim through the same function the registration columns use, so
what this module asserts is *behaviour through provisioning* rather than the rules
themselves — those are asserted once, from both sides, in
`tests/unit/test_registration_address_constraints.py`, and the values below are
that module's own so a reader can put the two side by side.

**A refused address is not a refused section.** The ruling: the address stays
NULL, `roster_address_refused` is recorded, and the section is still provisioned.
SPEC §7.3 says why in as many words — "Where a platform withholds the address even
from a staff launch, the section has no roster and no sync can be attempted: the
admin console shows it as never-synced (§6.1, §6.3) rather than as empty, because
a section with no roster and a section with no enrollments are different states
and only one of them is a fault." A refused address puts the section in exactly
that state, and refusing the whole launch instead would take a real course out of
the product over a URL.

**Everything here runs outside development, and that is not incidental.** Every
rule the chokepoint applies is switched off under the development name so the demo
stack can seed the mock's own cleartext addresses on a Compose service name. A
refusal test in development would assert nothing at all, so `launch_driver_in`
builds the application under a deployment's `ENVIRONMENT` — which is also what
makes the acceptance rows below mean something, since they are accepted under the
same name that refuses their neighbours.

**Rule 5 reaches this surface too, and it reversed one of these rows.** The
cleanup batch resolves the host and refuses any returned address that is not
globally routable, so a private address advertised in a launch claim is no longer
stored. `provision_from_launch` passes neither the resolver nor an exempt host:
in development the blanket admission is unchanged, and in a deployment it resolves
with real DNS — one lookup on a rare staff launch, accepted deliberately. That is
why every vector below is an IP literal or a value rules 1 to 4 refuse before
anything is looked up: nothing in this suite may depend on what a name server
answered.

**Every launch here also carries an acceptable gradebook address, and that is
E3-02 arriving.** That ticket puts the AGS endpoint claim's `lineitems` member
through this same chokepoint and records a defect of its own when it is refused —
so the mock's own cleartext container address would put a second defect on every
launch below, and the assertions here are written over exactly one. The fixture
rewrites it to a globally routable literal, which changes nothing about what this
module is for: the roster address stays the only thing under test, and it stays the
only thing a defect here can be about.

**Driven at the writer with one member rewritten.** The mock platform advertises
one roster address and no mint changes it, so the claims are a real launch's from
the registered platform, with the NRPS claim's `context_memberships_url` replaced
and nothing else touched. `test_a_staff_launch_stores_the_roster_service_address_from_its_own_claim`
in `tests/integration/test_launch_time_provisioning.py` is the door-driven half:
the ordinary path, in development, storing the address the platform really sent.
"""

from typing import Any

import pytest

pytestmark = [pytest.mark.integration, pytest.mark.lti]

# A deployment's `ENVIRONMENT`. Every rule the chokepoint applies is conditioned on
# not being the development name, so this is the name under which this module has
# a subject at all.
PRODUCTION = "production"

# The values, taken from `tests/unit/test_registration_address_constraints.py` so
# the two modules can be read side by side. Each refused row carries `https`, so
# the transport rule cannot be what refuses it and a green row cannot be
# misattributed to the wrong rule (`docs/MISTAKES.md` entry 3) — except the
# cleartext row, whose whole subject is the transport.
DEPLOYED_HOST = "lms.example.edu"

REFUSED_ADDRESSES = {
    "the cloud metadata service": "https://169.254.169.254/latest/meta-data/",
    "another address in the link-local range": "https://169.254.0.1/memberships",
    "the IPv6 link-local literal": "https://[fe80::1]/memberships",
    "cleartext to another host": f"http://{DEPLOYED_HOST}/lti/memberships",
    # Rule 5's own rows, and the reversal it carries. These three were in
    # `ACCEPTED_ADDRESSES` under ADR 0081's four rules — that record accepted
    # private ranges everywhere and rejected `not ip.is_global` by name — and the
    # cleanup batch refuses them, because a resolved private address is the
    # residual finding E1-11 recorded and nothing at the point of judgment tells
    # an institution's own LMS from an internal service holding a valid
    # certificate. A launch claim is the *front door* for that value: a platform
    # advertises the address and this tool stores it.
    "an RFC 1918 address": "https://10.0.0.5/lti/memberships",
    "another RFC 1918 address": "https://10.0.0.7/lti/memberships",
    "an IPv6 unique local address": "https://[fd00::5]/lti/memberships",
}

# The other direction, and the half this rule stands or falls on: an address a
# real platform advertises and this tool must go on storing. Both rows are IP
# literals rather than hostnames, and that is forced rather than chosen —
# `provision_from_launch` passes no resolver, so under a deployment it resolves
# with the machine's own name server, and a hostname here would make this suite's
# result depend on what DNS answered (`docs/MISTAKES.md` entry 40's shape). A
# literal is resolved without a query.
#
# **Neither is in a documentation range**: `203.0.113.0/24` and `192.0.2.0/24`
# read like public addresses and report `is_global` false, so either would be
# refused by rule 5 and this whole pair would assert nothing.
ACCEPTED_ADDRESSES = {
    "a globally routable address": "https://93.184.216.34/lti/memberships",
    "a globally routable IPv6 address": "https://[2606:4700:4700::1111]/lti/memberships",
}

# The gradebook address every launch in this module carries, and it is here so that
# the *roster* address is the only thing a defect below can be about. E3-02 puts the
# AGS endpoint claim's `lineitems` member through this same chokepoint and records a
# defect of its own when it is refused, and the mock advertises that container at
# `http://mock-lms:8000/...` — cleartext, on the mock's own host, which is refused
# twice over under a deployment's name. Left alone, every launch here would carry a
# second refusal and `the_one(rows.defects())` below would find two rows
# (`docs/MISTAKES.md` entry 22: a later ticket's rule making an earlier ticket's
# tests unrunnable). A globally routable literal, for the same reason the accepted
# rows above are literals: nothing in this suite may depend on what a name server
# answered.
AN_ACCEPTED_GRADEBOOK_ADDRESS = "https://93.184.216.34/lti/lineitems"


def the_one(rows: list[Any], what: str) -> Any:
    """Exactly one row, or a failure saying which of the two failures happened."""
    assert (
        len(rows) == 1
    ), f"There are {len(rows)} rows where there should be exactly one {what}: {rows}."
    return rows[0]


def provision(provisioning: Any, session: Any, claims: Any) -> BaseException | None:
    """Run the writer over one launch's claims, answering an escaped exception.

    Answering rather than raising, so the forbidden state — the address is not
    stored — is asserted whichever way the refusal is expressed, and so a refusal
    that escaped is reported as itself rather than as a missing row.
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

    The application is built with `ENVIRONMENT` set to a deployment's name, which
    is what puts the registration-address rules in force at all — under the
    development name they accept everything, deliberately, and every refusal below
    would be asserting nothing.

    Building the tool is how the variable is set: `tool_doors` lays it down before
    importing the application, so a module that reads `Settings` at import is
    built under it and one that reads it per call sees it too
    (`docs/MISTAKES.md` entry 3). Nothing here drives a request through that tool —
    the claims are rewritten and handed to the writer directly — but the import it
    forced is the point.
    """
    driver = launch_driver_in(PRODUCTION)
    offer = driver.offer_for_role(provisioning_contract.instructor_role_urn)
    claims = provisioning_contract.with_line_items_url(
        driver.claims_of(offer), AN_ACCEPTED_GRADEBOOK_ADDRESS
    )
    launch_ground(provisioning_contract.label_of(claims))
    return {"claims": claims, "rows": rows_on(db_session), "session": db_session}


@pytest.mark.parametrize("spelling", sorted(REFUSED_ADDRESSES))
def test_a_roster_address_the_registration_rules_refuse_is_not_stored(
    deployed_launch: dict[str, Any],
    provisioning_contract: Any,
    provisioning: Any,
    spelling: str,
) -> None:
    """The MEDIUM, driven: an address this container will fetch is judged before it is kept.

    The link-local rows are the finding. `169.254.169.254` answers instance
    credentials to anything inside the container that asks, and E1-11 fetches this
    column with the tool's own client assertion on a schedule — so an address
    stored here is an unauthenticated request the tool makes on somebody else's
    behalf, from inside the network boundary, with nobody watching. `169.254.0.1`
    is there because a rule written against the one famous address leaves the rest
    of the range, and `[fe80::1]` because a rule written over the IPv4 block alone
    leaves the IPv6 half — both are E1-05's own rows, for E1-05's own reasons.

    The cleartext row is a different rule reaching the same column: an address
    fetched over plain HTTP is a roster, with names and email addresses in it,
    delivered to anyone on the path.

    **What is asserted is the forbidden state and the state §7.3 names.** The
    column is NULL — not the platform's value, not a repaired one — the defect is
    recorded, and the section still exists. A launch refused outright over a URL
    would take a real course out of the product; SPEC §7.3 makes never-synced a
    state rather than a fault.

    **The mutation this kills**: the `isinstance(str)` check the review found, and
    any second copy of the rules written beside the chokepoint rather than routed
    through it — a copy would have to be found and fixed twice, which is
    `docs/MISTAKES.md` entry 13's shape.

    **Its pair** is `test_a_roster_address_the_registration_rules_allow_is_stored`
    below, under this same environment: without it, every row here is satisfied by
    a writer that never stores an address at all.
    """
    address = REFUSED_ADDRESSES[spelling]
    rows = deployed_launch["rows"]
    claims = provisioning_contract.with_memberships_url(deployed_launch["claims"], address)

    escaped = provision(provisioning, deployed_launch["session"], claims)

    section = the_one(rows.sections(), "section")
    stored = section[provisioning_contract.section_address_column]
    assert stored is None, (
        f"The section carries `{provisioning_contract.section_address_column}` = {stored!r} after "
        f"a launch advertising {address!r}, which "
        "`app.models.lti.refuse_invalid_registration_addresses` refuses on every address this "
        "container fetches. E1-11 calls this column with the tool's own credentials — so a stored "
        "value is a request the tool makes to wherever the claim said, from inside the network "
        "boundary. `tests/unit/test_registration_address_constraints.py` is where the rule itself "
        "is asserted; this is the column it now reaches."
    )
    recorded = the_one(rows.defects(), "recorded defect")
    kind = str(getattr(recorded["kind"], "value", recorded["kind"]))
    assert kind == provisioning_contract.roster_address_refused, (
        f"The recorded defect's kind is {kind!r} and a refused roster address is "
        f"{provisioning_contract.roster_address_refused!r}. E11's surface reads this to tell an "
        "administrator that a section is never-synced *because its platform advertised an address "
        "we will not call*, which is a different conversation from any other defect here."
    )
    assert escaped is None, (
        f"The address was not stored, which is this test's subject and holds — but the refusal "
        f"escaped as {escaped!r}. §7.3 makes a section with no roster a state and not a fault, so "
        "a launch may not fail over one."
    )


@pytest.mark.parametrize("spelling", sorted(ACCEPTED_ADDRESSES))
def test_a_roster_address_the_registration_rules_allow_is_stored(
    deployed_launch: dict[str, Any],
    provisioning_contract: Any,
    provisioning: Any,
    spelling: str,
) -> None:
    """The near miss, under the same deployment name that refuses the rows above.

    Two addresses a real platform advertises: a globally routable IPv4 address and
    a globally routable IPv6 one. This pair used to carry the private ranges as
    well, on ADR 0081's reasoning that an institution running its LMS on RFC 1918
    space is an ordinary deployment; rule 5 reverses that, and those rows are in
    `REFUSED_ADDRESSES` now with the reversal written down beside them. What stays
    here is the half without which every refusal above is satisfied by a writer
    that stores nothing at all.

    The IPv6 row is not decoration: a rule 5 written over the IPv4 classes alone
    refuses every address it cannot classify, or accepts every one, and either way
    this row is the only thing in the module that says which.

    **The mutation this kills**: any refusal wider than the chokepoint's — a
    scheme allow-list, a rule that refuses every IP literal, a rule 5 that refuses
    whenever it resolved anything at all. Each of those passes every row above and
    silently stops the roster sync for deployments nobody would think to test.

    Nothing is recorded on this path either: a defect per successful launch would
    make E11's surface noise, which is what
    `test_a_launch_with_everything_seeded_records_no_defect` holds generally and
    what this asserts for the address in particular.
    """
    address = ACCEPTED_ADDRESSES[spelling]
    rows = deployed_launch["rows"]
    claims = provisioning_contract.with_memberships_url(deployed_launch["claims"], address)

    escaped = provision(provisioning, deployed_launch["session"], claims)

    assert escaped is None, f"Provisioning a launch advertising {address!r} raised {escaped!r}."
    section = the_one(rows.sections(), "section")
    assert section[provisioning_contract.section_address_column] == address, (
        f"The section carries {section[provisioning_contract.section_address_column]!r} and its "
        f"platform advertised {address!r}. §7.3 has the address arrive as a claim and be stored, "
        "and this one is an address the registration rules accept — refusing it leaves a real "
        "institution's section never-synced for no reason, which no test of the refusals above "
        "would notice."
    )
    assert not rows.defects(), (
        f"A launch advertising an acceptable roster address recorded {rows.defects()}. The defect "
        "table is a surface a human reads and acts on."
    )
