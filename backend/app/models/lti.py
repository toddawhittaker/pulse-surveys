"""The LTI 1.3 registration: which platforms may launch this tool, and from where.

SPEC §7.3 and §8. A registration is what a launch is validated against — the
issuer that signed the `id_token`, the client ID it was issued for, the
deployment it came from, and the key set the signature is checked with. E0-18's
launch door reads both tables today: `app.lti.launch.registered_platform` looks
a platform up by issuer, and `registered_deployment` refuses a launch naming a
deployment nobody registered under it.

**No secret is stored, and that is the design rather than an omission.** LTI 1.3
is asymmetric: the platform signs, and the tool verifies with public keys it
fetches from the platform's JWKS URL. There is no shared secret in the protocol
to store, so E0-08 criterion 7 — "`lti_platform` stores no client secret in
plaintext, and a test asserts the column either does not exist or is encrypted at
rest" — is met by the column not existing. `jwks_url` is a public address and the
keys behind it are public keys.

The tool's *own* signing key is the one piece of key material an LTI 1.3
deployment needs, and E0-08 deliberately did not add it: nothing then read it,
and a key sitting in a table no code opens is a credential at rest with no owner.
**E1-05 adds it, as `ToolSigningKey` below**, one row ahead of E1-06's signing
code by one ticket — the two move together across E1-05/E1-06 because the
registration document's keys are the column names on both sides. It still adds no
configuration variable: custody is the database (`docs/adr/0082`), the seed
generates it in development, and no `app.config.Settings` field resolves to it,
which is what the epic README's rule keys the `.env.example` line on.

**The platform's service addresses arrived here in E1-05.** §7.3 leaves the OIDC
authorization endpoint to the registration, and E0-23 put the columns for it in
E1, with the code that reads them (`docs/adr/0075`); `authorization_endpoint` and
`auth_token_url` below are them. E0-08's scope named issuer, client ID,
deployment IDs, JWKS URL and last fetch, which is what this module built until
now.

**What a legitimate address is, is decided here too** (`docs/adr/0081`, and
`docs/adr/0101` for rule 5). `refuse_invalid_registration_addresses` below is the
chokepoint every writer of an `lti_platform` row passes through, and the mapper
events at the foot of this module are what make that a property of the model
rather than something each writer has to remember. E0-24 item 1 left `jwks_url`
credential-equivalent and unconstrained — it decides which keys may sign an
accepted launch, and it is fetched server-side on every launch — and E1 is the
epic that writes and fetches it, so E1 says what it may hold.

**The launch-time records live here too, beside the registration they are about.**
`LtiLaunchNonce` and `LtiLaunchState` are E1-08's replay ledger and in-flight
handshake, and `LaunchDefect` is E1-10's append-only record of a launch whose
context could not be ingested. None of the three is a registration, and all three
are keyed by what a launch carries — an issuer, a deployment, a nonce, a state —
so SPEC §13's "one module per aggregate" puts them with the tables those values
resolve against rather than with the org hierarchy a defect happens to name.

**Nothing here is marked LMS-owned.** An `lms_` prefix (ADR 0014) marks a column
Pulse may never edit. A registration is typed into the admin console by an
administrator (SPEC §2, Admin: "LTI registration"), so every column in this
module is Pulse's to write. `user.lms_user_id` in `app.models.identity` is the
contrasting case: the `sub` claim arrives from the platform and Pulse never
chooses it.
"""

import ipaddress
import socket
from collections.abc import Callable, Sequence
from datetime import datetime
from enum import StrEnum
from urllib.parse import urlsplit
from uuid import UUID

import requests
from requests.models import PreparedRequest
from sqlalchemy import Connection, Enum, ForeignKey, Index, Text, UniqueConstraint, event, text
from sqlalchemy.orm import Mapped, Mapper, mapped_column, object_session

# ADR 0077's host vocabulary, imported rather than re-derived. Each of these
# answers a question this module asks in exactly the same words: is this
# environment a deployment, what is this URL's host once one trailing dot comes
# off, does the host name the machine *this* container runs on, does it name the
# machine the *reader* of the URL sits at. The trailing-dot strip and the
# IPv4-mapped unwrap are parsing quirks that were found the hard way, and a
# second derivation of either is `docs/MISTAKES.md` entry 13 exactly — a hazard
# worked around in one of the two places facing it.
#
# They carried a leading underscore while `app.config` was their only caller.
# This module is the second, so the underscore stopped being true and they lost
# it.
from app.config import (
    is_a_deployment,
    is_a_loopback_host,
    is_on_this_machine,
    url_host,
)
from app.models.base import AwareDateTime, Base, UuidPrimaryKey

__all__ = [
    "LaunchDefect",
    "LaunchDefectKind",
    "LtiDeployment",
    "LtiLaunchNonce",
    "LtiLaunchState",
    "LtiPlatform",
    "RegistrationAddressError",
    "ToolSigningKey",
    "refuse_invalid_fetched_address",
    "refuse_invalid_registration_addresses",
]

# The Compose service the in-repo mock platform runs as (SPEC §7.2). A
# registration naming it outside development is refused: the mock authenticates
# nobody and signs a launch as whatever subject the caller picks, so trusting it
# in a deployment is a signing oracle for fake identities (ADR 0038, ADR 0068).
#
# The service name and not the seeded URL. A container on this network reaches
# the mock at `mock-lms` on whatever port it listens on, so comparing against
# `http://mock-lms:8000/...` is defeated by an operator who changes the port or
# terminates TLS in front of it. ADR 0077 refuses `mock-idp` the same way and
# for the same reason.
MOCK_PLATFORM_SERVICE = "mock-lms"

# The three columns the chokepoint judges, named so a refusal can say which one
# carries the offending value without quoting it (ADR 0056's house rule).
AUTHORIZATION_ENDPOINT_COLUMN = "authorization_endpoint"
JWKS_URL_COLUMN = "jwks_url"
AUTH_TOKEN_URL_COLUMN = "auth_token_url"  # noqa: S105 - a column name, not a credential

# E1-10's roster service address, which is not a registration column at all: it
# arrives on a launch as an NRPS claim and is stored on `section`. It is named
# here because the rules below key on a column name, and this is a column this
# container **fetches** — E1-11 calls it with the tool's own client credentials,
# on a schedule, with nobody present — so rule 4 has to reach it. E1-10's round-3
# security review is why: before it the roster address reached the column on an
# `isinstance(str)` check, and `169.254.169.254` was a value a launch could name.
ROSTER_SERVICE_ADDRESS_COLUMN = "lms_context_memberships_url"

# E3-02's two gradebook addresses, which are not registration columns either and
# which reach these rules for the same reason the roster address does.
#
# `section.lms_ags_line_items_url` is the AGS line-item **container** for one
# launched context. It arrives on a staff launch as the `lineitems` member of the
# AGS endpoint claim and is stored exactly as the roster address is; the platform
# publishes it and Pulse never edits it, which is what the `lms_` marker means (ADR
# 0014). `section.ags_line_item_url` is the id of the line item this tool
# **creates** in that container — SPEC §3.4's one line item per section — which is
# Pulse's own doing and so carries no marker. E3-02 adds both columns and writes
# only the first; E3-05 is the writer of the second.
#
# Both are addresses this container fetches with the tool's own client credentials,
# on a schedule, with nobody present: E3-04 lists and creates in the container, and
# E3-05 and E3-06 post scores to the line item. That is the same server-side
# request forgery surface the roster address is, arriving through a second claim,
# so the answer is these same enumerations rather than a second scheme beside them.
AGS_CONTAINER_ADDRESS_COLUMN = "lms_ags_line_items_url"
AGS_LINE_ITEM_ADDRESS_COLUMN = "ags_line_item_url"

# The five this container fetches, as opposed to the one it hands to a browser.
# Rules 3 and 4 below are the whole of that distinction.
FETCHED_COLUMNS = (
    JWKS_URL_COLUMN,
    AUTH_TOKEN_URL_COLUMN,
    ROSTER_SERVICE_ADDRESS_COLUMN,
    AGS_CONTAINER_ADDRESS_COLUMN,
    AGS_LINE_ITEM_ADDRESS_COLUMN,
)

# The columns loopback is refused on, and E1-11's security round widened it. Rule 3
# began as `authorization_endpoint` alone — the one address a *browser* resolves, so
# loopback there is the launching person's own computer. The roster service address
# joins it, and only it, because of who chooses the value. `jwks_url` and
# `auth_token_url` are written by the registration writer under an operator's own
# hand, and a platform component running as a loopback sidecar in the same pod is an
# ordinary deployment ADR 0077 protects by name — which is why loopback is *accepted*
# on those two (`tests/unit/test_registration_address_constraints.py::test_a_loopback_
# fetched_address_is_accepted_outside_development`). The roster address's *pagination
# next URL* is a different thing entirely: it is chosen by the platform at fetch time,
# an untrusted source, so a loopback there is a service on this container that the
# operator never pointed the tool at — the textbook server-side request forgery. ADR
# 0096 records why the two fetched columns split here where rule 4 (link-local) keeps
# them together.
#
# **E3-02's two gradebook addresses join it, and the split decides them the same
# way.** ADR 0096 admits loopback on the columns an *operator* writes by hand and
# refuses it on the ones a *platform* chooses at run time. Both gradebook addresses
# are the platform's: the container is advertised in a launch claim, and the line
# item's own id is whatever the platform answers when this tool creates one. So a
# loopback in either is a service on this container that nobody registered, which
# is the request forgery the roster address's own round found.
LOOPBACK_REFUSED_COLUMNS = (
    AUTHORIZATION_ENDPOINT_COLUMN,
    ROSTER_SERVICE_ADDRESS_COLUMN,
    AGS_CONTAINER_ADDRESS_COLUMN,
    AGS_LINE_ITEM_ADDRESS_COLUMN,
)

# The port rule 5's resolution is asked under. `getaddrinfo` wants a service as
# well as a host, and every address judged here is opened over TLS in the case
# that matters, so 443 is the honest one to ask with — the addresses a host
# answers with are the same either way.
RESOLUTION_PORT = 443

# The key a session states its environment under, for the mapper events at the
# foot of this module. Written down once and imported by the writers that stamp
# it (`app.db`, `scripts/seed.py`): a writer stamping a different spelling would
# be judged as a deployment and refused with nothing to say why
# (`docs/MISTAKES.md` entry 13).
ENVIRONMENT_SESSION_KEY = "environment"

# What a write is judged under when nobody said where it was made — the mapper
# events at the foot of this module read `Session.info["environment"]`, and a
# session that carries none gets this. It is a deployment by `is_a_deployment`,
# which is the fail-closed direction: a legitimate development writer that has
# not said so is refused loudly on its first run, with a message naming the
# column and a one-line repair where the session is built, while the other
# reading lets a writer nobody thought about register the mock platform in
# production with nothing anywhere noticing.
UNSTATED_ENVIRONMENT = "unstated"


class RegistrationAddressError(Exception):
    """A registration states an address this environment will not accept.

    Names the column and never quotes the value, for the reason ADR 0056 gives
    about configuration refusals: this message reaches the seed's stderr, a
    container log and later E11's registration console, and a deployment's own
    addresses are not something to write into all three (SPEC §10). The host may
    appear — it is what is being refused.
    """


def _is_a_link_local_host(host: str | None) -> bool:
    """Whether this host is in `169.254.0.0/16` or `fe80::/10`.

    The two families together, because a rule written over the IPv4 range alone
    leaves the IPv6 half and a container with IPv6 reaches the same class of
    thing through it.

    **A third question about a host, and deliberately its own helper.**
    `app.config.is_on_this_machine` governs an *exemption* and
    `app.config.is_a_loopback_host` governs a refusal about the reader's
    machine; this one governs a refusal about what this container may fetch.
    Merging any two would mean a future widening moved both, and for two of the
    three that is in opposite directions of safety — which is the reasoning
    `is_a_loopback_host` already carries for not merging with the first.

    The IPv4-mapped form is unwrapped first, for the reason and by the shape
    `is_a_loopback_host` uses: it keeps both halves live rather than resting on
    a library behaviour that has moved between versions.
    """
    if not host:
        return False
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
        return address.ipv4_mapped.is_link_local
    return address.is_link_local


def _resolved_addresses(host: str) -> tuple[str, ...]:
    """Every address this machine's resolver answers for `host`, in the order given.

    Rule 5's default resolution, and the only place in `backend/` that asks a name
    server anything. It is a parameter everywhere it is used (`resolve`) so that a
    test can describe an answer instead of depending on what DNS said — a rule
    measured against a machine's resolver is green on one machine and red on
    another (`docs/MISTAKES.md` entry 40).

    De-duplicated with the order preserved, because the sync pins its connection
    to the first address and "the first" has to mean the resolver's first rather
    than a set's arbitrary one. An IP literal is answered by `getaddrinfo` without
    a query, so a literal host costs nothing here.
    """
    found: list[str] = []
    for *_family, sockaddr in socket.getaddrinfo(host, RESOLUTION_PORT, proto=socket.IPPROTO_TCP):
        address = str(sockaddr[0])
        if address not in found:
            found.append(address)
    return tuple(found)


# The two other /96 ranges that carry an IPv4 in their low 32 bits, beside the
# IPv4-mapped `::ffff:0:0/96` that `IPv6Address.ipv4_mapped` already reports. On a
# DNS64/NAT64 egress (SPEC §10, the IPv6-only network) the gateway translates a GET
# to either of these to the embedded IPv4, so a rule that judged the wrapper reads a
# different answer from the one the packet gets: `64:ff9b::a9fe:a9fe` reaches
# `169.254.169.254`. The IPv4-compatible form is deprecated (RFC 4291) but still
# routed, and it contains the specials `::` and `::1`, which are NOT an embedded
# IPv4 and are excluded below.
_NAT64_WELL_KNOWN_PREFIX = ipaddress.ip_network("64:ff9b::/96")
_IPV4_COMPATIBLE_PREFIX = ipaddress.ip_network("::/96")


def _embedded_ipv4(resolved: ipaddress.IPv6Address) -> ipaddress.IPv4Address | None:
    """The IPv4 an IPv6 address carries in its low 32 bits, or `None` if it carries none.

    Three IPv6 forms embed an IPv4 that a NAT64/DNS64 egress translates a packet
    to, and each has to be judged as the address the packet reaches rather than as
    the wrapper — `ipaddress` reports every one of them `is_global` true while the
    embedded address is internal:

      - the **IPv4-mapped** `::ffff:0:0/96`, which `.ipv4_mapped` already reports;
      - the **NAT64 well-known** `64:ff9b::/96` (RFC 6052);
      - the deprecated **IPv4-compatible** `::/96` (RFC 4291).

    The IPv4-compatible range contains `::` (unspecified) and `::1` (IPv6 loopback),
    which are not an embedded IPv4 and must keep their own identity — unwrapping
    `::1` to `0.0.0.1` would lose the loopback the module's split (ADR 0096) turns
    on. They are excluded, so the IPv6 loopback and unspecified handling below is
    left intact; an embedded `127.0.0.1` (`::7f00:1`) is a genuine IPv4-compatible
    address and is unwrapped.
    """
    if resolved.ipv4_mapped is not None:
        return resolved.ipv4_mapped
    if resolved in _NAT64_WELL_KNOWN_PREFIX or (
        resolved in _IPV4_COMPATIBLE_PREFIX
        and not resolved.is_loopback
        and not resolved.is_unspecified
    ):
        return ipaddress.IPv4Address(int(resolved) & 0xFFFFFFFF)
    return None


def _is_an_acceptable_resolved_address(column: str, address: str) -> bool:
    """Whether one address a host resolved to is one this column may reach.

    Globally routable is acceptable, and nothing else is — private (RFC 1918),
    carrier-grade NAT, link-local, reserved and loopback are all refused by the
    one question `ipaddress` already answers. The single exception is **loopback
    on a column outside `LOOPBACK_REFUSED_COLUMNS`**, which keeps ADR 0096's
    split: an operator registering a key-set or token sidecar reached at a
    loopback address in the same pod is doing it on purpose, and rule 5 adds a
    resolution dimension to that split rather than reopening it.

    An **embedded IPv4** is unwrapped first, by the shape and for the reason
    `_is_a_link_local_host` above and `app.config.is_a_loopback_host` both use:
    `::ffff:10.0.0.7`, `64:ff9b::a9fe:a9fe` and `::a9fe:a9fe` are internal IPv4
    addresses reached over an IPv6 socket on a NAT64 egress, and a rule that asked
    the wrapper reads a different answer from the one the packet gets. The three
    forms and the `::`/`::1` boundary live in `_embedded_ipv4`.

    An answer that does not parse as an address at all is refused, for the same
    reason an unresolvable host is: what cannot be judged is not something to
    reach.
    """
    try:
        resolved = ipaddress.ip_address(address)
    except ValueError:
        return False
    if isinstance(resolved, ipaddress.IPv6Address):
        embedded = _embedded_ipv4(resolved)
        if embedded is not None:
            resolved = embedded
    if resolved.is_global:
        return True
    return resolved.is_loopback and column not in LOOPBACK_REFUSED_COLUMNS


def _refuse_an_unacceptable_resolution(
    column: str, value: str, resolve: Callable[[str], Sequence[str]]
) -> tuple[str, ...]:
    """Rule 5, applied to one address: resolve the host and judge every answer.

    Rules 1 to 4 judge *spellings*, and ADR 0081 measured what that leaves:
    `127.1`, `2130706433`, `0x7f.0.0.1` and any name a resolver answers with a
    refused address walk past all four while reaching exactly the addresses they
    refuse. Rule 5 is the close, and it is a resolution rather than a fifth
    spelling because a name is not a spelling anybody can enumerate. ADR 0101.

    **Every returned address is judged, not the first.** A name with one public
    and one internal record is an ordinary split-horizon arrangement and is also
    the way past a rule that reads `resolve(host)[0]`; which record comes back
    first is the resolver's business and, for a hostile platform, its own DNS's.

    **An unresolvable host is refused, in both shapes.** A resolver can fail by
    raising and by answering nothing at all, and admitting either is the hole the
    whole rule is walked through: a name that resolves nowhere at the moment of
    the check resolves wherever its owner likes at the moment of the fetch.

    Answers the addresses it resolved, which is what the roster sync pins its
    connection to — the address that was judged is the address the request goes
    to. The refusal names the column and quotes neither the value nor the
    addresses: a deployment's internal addressing reaching a container log
    through a value a platform supplied is the same house rule one level in.
    """
    host = url_host(value)
    if host is None:
        raise RegistrationAddressError(
            f"The registration's `{column}` names no host at all, so there is nothing to resolve "
            "and nothing to judge. Register the platform's own address, or run with "
            "ENVIRONMENT=development."
        )

    unresolvable = RegistrationAddressError(
        f"The registration's `{column}` names a host this container cannot resolve to any "
        "address — either nothing answers for it, or it is not a name a resolver will encode at "
        "all. An address that cannot be resolved cannot be judged, and a name that resolves "
        "nowhere now resolves wherever its owner chooses at the moment this container fetches it. "
        "Register a platform address this container can resolve, or run with "
        "ENVIRONMENT=development."
    )
    # **Two exception families, because a resolver fails in two ways.** A host
    # nothing answers for raises `socket.gaierror`, an `OSError`. A host the
    # resolver will not *encode* — a label over 63 octets, an empty label —
    # raises `UnicodeError` from the IDNA codec, before any query is composed;
    # that is a `ValueError` and no `OSError` at all. Catching one of the two
    # left the other escaping these rules entirely: past the walk, which catches
    # only the refusal type, into the per-section handler that rolls the
    # transaction back — so no refusal row was written and the pages already
    # validly read went with it. E1 Batch C's security review found it.
    try:
        resolved = tuple(resolve(host))
    except (OSError, UnicodeError):
        raise unresolvable from None
    if not resolved:
        raise unresolvable

    for address in resolved:
        if not _is_an_acceptable_resolved_address(column, address):
            raise RegistrationAddressError(
                f"The registration's `{column}` names a host that resolves to an address this "
                "container will not reach: one that is not globally routable — a private range, "
                "the carrier-grade NAT range, link-local, loopback or reserved space. This tool "
                "fetches that address with its own credentials, and an internal service holding a "
                "valid certificate inside this network is indistinguishable here from a "
                "platform's own. Register an address on the public internet, or run with "
                "ENVIRONMENT=development."
            )
    return resolved


def _is_judged_in_development(address: str, development_exempt_host: str | None) -> bool:
    """Whether rule 5 runs in development for this fetched address.

    Only for a host that is **not** the one the caller named as its own. A
    development stack's stored roster address is the operator's own — judged at
    registration-write time, where development deliberately admits the mock — and
    the hourly walk would otherwise pay a name lookup for it once per page of
    every section, on a stack whose platform is a Compose service that half the
    time resolves to nothing. A `rel="next"` hop to any *other* host is a value
    the platform chose, and it is judged.

    Equality on the parsed host, never a substring: `mock-lms.evil.example` is a
    host somebody else controls, and a prefix comparison would hand it the whole
    of rule 5. The exempt host goes through `url_host` as well, so both sides are
    read the way a resolver reads them — folded, and with one trailing dot off
    (`docs/MISTAKES.md` entry 13: one normalisation, applied at both ends).

    A caller that names no exempt host gets development's blanket admission,
    which is what `app.services.provisioning` passes at launch-time storage.
    """
    if development_exempt_host is None:
        return False
    return url_host(address) != url_host(f"//{development_exempt_host}")


def refuse_invalid_registration_addresses(
    environment: str,
    *,
    authorization_endpoint: str | None,
    jwks_url: str,
    auth_token_url: str | None,
    resolve: Callable[[str], Sequence[str]] | None = None,
) -> None:
    """Refuse a registration whose addresses this environment will not accept.

    The chokepoint every writer of an `lti_platform` row passes through, and
    since ADR 0101 that is structural rather than a convention: the mapper events
    at the foot of this module call it on every ORM insert and update of
    `LtiPlatform`, so a writer that never heard of it — E11's registration
    console, a script, a service in a later epic — is judged anyway. `scripts/seed.py`
    also calls it directly, before it builds a flush at all, and that is belt and
    braces rather than the guarantee. E0-24 item 1 left `jwks_url`
    credential-equivalent and unconstrained, and E1 writes and fetches it, so E1
    says what a legitimate value looks like. `docs/adr/0081` is that decision and
    states where ADR 0077's vocabulary carries over; `docs/adr/0101` adds rule 5
    and supersedes 0081 in part.

    **A validator rather than a `CHECK` constraint**, because every rule reads
    `ENVIRONMENT` and the database does not hold it. The residue is the write
    shapes no mapper event fires for — measured, and listed on the events at the
    foot of this module rather than guessed at here; ADR 0081 and ADR 0101 both
    record it rather than hiding it.

    **NULL passes.** Both new columns are nullable and absence means "not
    stated", never a default. A NULL `authorization_endpoint` is refused at the
    *launch* (`app.lti.launch.begin_a_launch`), not at the write.

    Six rules, all of them switched off where `environment` is exactly the
    development name — the mock's own addresses have to seed, and a rule that
    kept firing there would meet a developer as an unexplained refusal from
    `make seed`:

      1. **https**, with the on-this-machine exemption ADR 0077 rule 4 carries:
         a cleartext sidecar addressed by loopback stays deployable.
      2. **The mock platform's host is refused** on all three columns.
      3. **Loopback is refused on `authorization_endpoint`**, as a class, and on
         neither registration column this function judges. That string is resolved
         on the *reader's* machine, so loopback there is the launching person's own
         computer; `jwks_url` and `auth_token_url` are resolved here, where a
         sidecar the operator registers is an ordinary deployment. (The roster
         service address is not a registration column and is judged by
         `refuse_invalid_fetched_address`, where loopback *is* refused because its
         pagination URL is the platform's to choose — E1-11's round, ADR 0096.)
      4. **Link-local is refused on the two fetched columns.** They are the only
         addresses a stored row makes this container fetch, the cloud metadata
         service lives at `169.254.169.254`, and no legitimate LMS does.
      5. **The host is resolved and every returned address is judged** (ADR
         0101). An address that is not globally routable is refused — private
         ranges included, which reverses ADR 0081's acceptance of them and is the
         price that record named for the other direction. The one exception is
         loopback on a column outside `LOOPBACK_REFUSED_COLUMNS`, which keeps ADR
         0096's sidecar split; an unresolvable host is refused outright.
      6. **The judged host and the dialled host must be the same**, on
         `jwks_url` and `auth_token_url` — the two columns this container fetches.
         `_refuse_a_disputed_authority` is the same check the fetched column takes,
         and it is here because rule 5 does not backstop it: `10.0.0.5\\@public
         .example` is judged and resolved as `public.example`, globally routable,
         while the client dials `10.0.0.5`. `auth_token_url` is where the tool
         posts its signed client assertion, so a divergence there hands a credential
         to a host nobody judged. `authorization_endpoint` is deliberately not
         covered: a browser fetches it, not this container, the same stance rule 4
         takes.

    **Rule 5 runs after rules 1 to 4 and rule 6 have judged the whole
    registration**, so an address a spelling rule refuses is never looked up
    (`docs/MISTAKES.md` entry 29: a value handled before the check that should
    have refused it).

    Rules 1 and 3 **compose rather than short-circuit**: `http://localhost:8080`
    on the browser-facing column is exempt from the transport rule and refused by
    the loopback rule, and an exemption written as an early return would leave
    exactly the value an operator carries forward from the development stack.
    """
    if not is_a_deployment(environment):
        return

    addresses = {
        AUTHORIZATION_ENDPOINT_COLUMN: authorization_endpoint,
        JWKS_URL_COLUMN: jwks_url,
        AUTH_TOKEN_URL_COLUMN: auth_token_url,
    }
    stated = [(column, value) for column, value in addresses.items() if value is not None]
    for column, value in stated:
        _refuse_an_unacceptable_address(column, value)
    for column, value in stated:
        if column in (JWKS_URL_COLUMN, AUTH_TOKEN_URL_COLUMN):
            _refuse_a_disputed_authority(column, value)
    for column, value in stated:
        _refuse_an_unacceptable_resolution(
            column, value, _resolved_addresses if resolve is None else resolve
        )


def refuse_invalid_fetched_address(
    environment: str,
    *,
    column: str,
    address: str | None,
    resolve: Callable[[str], Sequence[str]] | None = None,
    development_exempt_host: str | None = None,
) -> tuple[str, ...] | None:
    """Judge one address this container fetches, by the rules above and no others.

    E1-10's roster service address (`section.lms_context_memberships_url`) is the
    third address in this system that this container fetches: it arrives on a
    launch as an NRPS claim, and E1-11 calls it with the tool's own client
    credentials, on a schedule, with nobody present. It is not a registration
    column, so `refuse_invalid_registration_addresses` above cannot judge it — and
    a second copy of the rules would be `docs/MISTAKES.md` entry 13, a hazard
    worked around in one of the two places facing it. So both callers reach the
    same five rules through `_refuse_an_unacceptable_address` and
    `_refuse_an_unacceptable_resolution`, and this one exists to supply the three
    things those functions cannot infer: the environment gate, that `None` is
    "not stated" rather than a value to judge, and which host in development is
    the caller's own.

    `column` is the name a refusal quotes, and it decides which rules apply —
    which is why `ROSTER_SERVICE_ADDRESS_COLUMN` is in `FETCHED_COLUMNS` above.

    **Loopback is refused on this column, which E1-11's security round decided and
    which is not true of the two registration columns beside it** (see
    `LOOPBACK_REFUSED_COLUMNS`). A roster URL points a server-side fetch, and the
    *pagination* address it follows is chosen by the platform at fetch time — so a
    loopback there reaches a service on this container that nobody registered, which
    is the server-side request forgery the review found. `jwks_url` and
    `auth_token_url` keep accepting loopback because an operator registers a sidecar
    through them on purpose; ADR 0096 records the split.

    **The two gates are not the same gate** (ADR 0101). Rules 1 to 4 are the
    deployment's, exactly as they were. Rule 5 runs always in a deployment — the
    stored address included, because a registration console writes it and a launch
    claim can carry it — and in development only when the caller names its own
    host and the address is somewhere else. `app.services.roster_sync` names the
    section's stored host, so the demo stack's own roster costs no lookup while a
    `rel="next"` hop anywhere else is judged; `app.services.provisioning` names
    none, so launch-time storage keeps development's blanket admission.

    **Rule 6, `_refuse_a_disputed_authority` below, refuses an address whose judged
    host and dialled host differ** — the E1 boundary round's security finding. It
    runs here on the fetched column, where a `rel="next"` is a value the *platform*
    chooses at fetch time, and it runs in `refuse_invalid_registration_addresses`
    on `jwks_url` and `auth_token_url` too, because rule 5 does not backstop the
    divergence: a `\\@`-form judged as a public name resolves globally and passes
    while the client dials the private host inside it.

    It runs wherever rule 5 runs, in development as well, because where the packet
    goes is not a property of the environment. And it runs *before* the resolution,
    so an address that cannot be dialled honestly is never looked up
    (`docs/MISTAKES.md` entry 29).

    Answers the addresses rule 5 resolved, or `None` where it did not resolve at
    all. The roster sync pins its connection to what comes back: the address that
    was judged is the address the GET goes to.
    """
    if address is None:
        return None
    # The parse every rule below depends on, forced once and turned into a refusal
    # if it fails, before any rule — or `_is_judged_in_development` — reads the host
    # and lets a `ValueError` escape the family the walk catches (rule 5's comment
    # claims this closed; this is where it is). In every environment, because an
    # unparseable authority is nobody's legitimate address.
    _judged_host_or_refuse(column, address)
    if is_a_deployment(environment):
        _refuse_an_unacceptable_address(column, address)
    elif not _is_judged_in_development(address, development_exempt_host):
        return None
    _refuse_a_disputed_authority(column, address)
    return _refuse_an_unacceptable_resolution(
        column, address, _resolved_addresses if resolve is None else resolve
    )


def _judged_host_or_refuse(column: str, value: str) -> str | None:
    """`url_host(value)`, with a parse failure turned into a refusal (rule 5's family).

    `url_host` runs `urlsplit`, which raises `ValueError` on an authority carrying a
    stray `[` or `]` (`Invalid IPv6 URL`), and `canonical_host` runs urllib3's
    parser, which raises on some others. A bare `ValueError` is not a
    `RegistrationAddressError`, and the roster walk catches only the latter — so an
    unparseable `Link` header escaped every rule here, reached the per-section
    handler, rolled the savepoint back, and cost the section its `nrps_call` row
    *and* the members already read rather than one page. Rule 5's own comment
    already claimed this family closed; this is where it becomes true, at the one
    parse every rule in this module depends on.

    A URL that names no host answers `None`, which each caller reads as "not a host
    to judge" — the empty-host refusal an operator can act on is rule 5's, not this.
    """
    try:
        return url_host(value)
    except ValueError as unparseable:
        raise RegistrationAddressError(
            f"The registration's `{column}` carries an authority no URL parser here can read "
            f"({unparseable}). An address whose host cannot even be parsed cannot be judged and "
            "must not be fetched; a `Link` header of this shape would otherwise abort the whole "
            "walk in an exception the caller does not catch. Register a well-formed address, or "
            "run with ENVIRONMENT=development."
        ) from None


def _dialled_host(value: str) -> str | None:
    """The host `requests` will actually dial for this URL, or `None` if it cannot.

    `PreparedRequest.prepare_url` is exactly what `Session.send` runs before it
    opens a socket, so this is the dialled authority itself rather than a model of
    it. Reading it back through `url_host` puts it in the same spelling the judged
    host is read in — one normalisation, `canonical_host`, applied at both ends
    (`docs/MISTAKES.md` entry 13), so a non-ASCII host that both sides IDNA-encode
    reads as one host rather than as a divergence.

    `None` for a URL `requests` refuses to prepare at all: no scheme, a label it
    will not encode, an authority it reads as malformed. The caller reads that as a
    divergence — an address that cannot be prepared cannot be dialled honestly, and
    refusing it is the fail-closed direction.
    """
    request = PreparedRequest()
    try:
        request.prepare_url(value, None)
    except (requests.RequestException, UnicodeError, ValueError):
        return None
    try:
        return url_host(str(request.url))
    except ValueError:
        return None


def _refuse_a_disputed_authority(column: str, value: str) -> None:
    """Rule 6: the host that was judged is the host that will be dialled.

    Every rule above reads the host out of `url_host` — `urlsplit` then
    `canonical_host`. The client that then fetches the address is `requests`, and
    the two do not always agree about where an authority ends. A raw backslash is
    the measured case: WHATWG's URL standard makes `\\` a terminator and RFC 3986
    does not, so `https://internal.corp\\a.evil.example/memberships` is the whole
    string to the parser that judges and `internal.corp` to the client that dials.
    A percent-escape is another: `ex%41mple.com` is judged as written and dialled
    as `example.com`. There is no `@` needed and no single character to blame.

    Judge with the first and connect with the second, and **every rule in this
    module has been applied to a host the packet never goes to** — with the tool's
    access token attached, past the resolution pin (which pins the address resolved
    for the judged name, a name this request never asks for), and inside whatever
    network the worker sits in. It is ADR 0081's rules defeated one level out: not
    by a spelling they missed but by a parser they never consulted.

    **Stated as a property, not as a refused character** (`docs/MISTAKES.md` entry
    35: a catalog of spellings is defeated by the one nobody enumerated). The rule
    is that the two readings must be the same host, so whatever the next
    disagreement turns out to be is refused by the same line.

    **The comparison is between the two readings directly, each read once through
    `url_host` and no second time.** An earlier form of this rule ran the *judged*
    host back through the client's own parser before comparing — and a backslash
    inside the judged host truncated both sides identically, so the rule reported
    agreement about a name the packet would not go to, and a percent-escape did the
    same. `canonical_host` already spells a host the way the transport will:
    urllib3 IDNA-encodes a non-ASCII host, and `canonical_host` calls the same
    encoder, so `röster.example` is `xn--rster-jua.example` on *both* sides and
    reads as one host with no second preparation. Preparing again was not only
    unnecessary — it re-introduced the divergence it was meant to catch. Verified
    across every host shape this suite drives (IDN, punycode, a trailing dot, a
    port, userinfo, IPv4, IPv6, IPv4-mapped): each is accepted, and the backslash,
    the percent-escape, a space and a quotation mark are each refused.

    A value naming no host at all — `judged is None` — is left to rule 5, which
    refuses it in terms an operator can act on. A URL the client will not prepare —
    `dialled is None` — is a divergence and is refused here: the judged host is a
    real name and the address cannot be dialled to it.
    """
    judged = _judged_host_or_refuse(column, value)
    if judged is None:
        return
    dialled = _dialled_host(value)
    if dialled is not None and dialled == judged:
        return
    raise RegistrationAddressError(
        f"The registration's `{column}` is read as the host {judged!r} by the parser these rules "
        f"judge with and as {dialled!r} by the client that would fetch it. Every rule above would "
        "have been applied to a name the request never goes to, and the tool's own credentials "
        "would be presented wherever it does go. Register an address whose authority is spelled "
        "once, or run with ENVIRONMENT=development."
    )


def _refuse_an_unacceptable_address(column: str, value: str) -> None:
    """Rules 1 to 4 — the spelling rules — applied to one stated address.

    See the two callers above; rule 5, which resolves the host, is
    `_refuse_an_unacceptable_resolution` and runs after every one of these has
    passed.

    Extracted from `refuse_invalid_registration_addresses`'s own loop in E1-10
    round 3 and otherwise unchanged, so the rules have one home and both callers
    reach the same one. The environment gate stays with the callers: it is asked
    once per call there rather than once per address here, and a rule set that
    could not be reached without it would be harder to test than the one
    `tests/unit/test_registration_address_constraints.py` already covers.
    """
    host = url_host(value)

    # The scheme off the parse rather than off `startswith`, so a spelling
    # `urlsplit` reads as https and a string comparison does not — or the
    # other way round — cannot arise. `url_host` parses the same value the
    # same way, so one answer governs the host rules below.
    if urlsplit(value).scheme != "https" and not is_on_this_machine(host):
        raise RegistrationAddressError(
            f"The registration's `{column}` is not https and does not name a service on this "
            "machine, so a launch would put the address, its query and whatever it carries on "
            "the wire in clear. Register an https address, or run with "
            "ENVIRONMENT=development."
        )

    if host == MOCK_PLATFORM_SERVICE:
        raise RegistrationAddressError(
            f"The registration's `{column}` addresses the mock platform this repository ships, "
            f"the Compose service {MOCK_PLATFORM_SERVICE}. It authenticates nobody and signs a "
            "launch as whatever subject the caller picks, so a deployment that trusts it "
            "accepts forged identities. Register a real platform, or run with "
            "ENVIRONMENT=development."
        )

    if column in LOOPBACK_REFUSED_COLUMNS and is_a_loopback_host(host):
        if column == AUTHORIZATION_ENDPOINT_COLUMN:
            raise RegistrationAddressError(
                f"The registration's `{column}` names this machine — localhost or a loopback "
                "address. A browser, not this container, is what resolves it, so loopback there "
                "is the launching person's own computer, and whatever listens on that port "
                "receives an authorization request arriving from a Pulse URL. Register the "
                "platform's own browser-facing address, or run with ENVIRONMENT=development."
            )
        raise RegistrationAddressError(
            f"The registration's `{column}` names this machine — localhost or a loopback "
            "address. This container fetches that address with the tool's own credentials, and "
            "a roster URL the platform chose that points at loopback reaches whatever this "
            "container runs beside — the server-side request forgery E1-11's review found in the "
            "pagination path. A sidecar the operator registers is reached through the two "
            "registration columns instead. Register the platform's own address, or run with "
            "ENVIRONMENT=development."
        )

    if column in FETCHED_COLUMNS and _is_a_link_local_host(host):
        raise RegistrationAddressError(
            f"The registration's `{column}` names a link-local address. This container fetches "
            "that column on every launch, and the link-local range is where a cloud provider's "
            "metadata service answers credentials to anything that asks. No platform is "
            "legitimately there. Register the platform's own address, or run with "
            "ENVIRONMENT=development."
        )


class LtiPlatform(UuidPrimaryKey, Base):
    """One registered LTI 1.3 platform — one issuer, one client ID.

    **Identified by the pair, not by the issuer alone.** A platform issues a
    client ID per tool registration, and one LMS can register this tool twice —
    a pilot alongside production is the ordinary case. So `UNIQUE (issuer,
    client_id)` and not a unique issuer, which would make the second registration
    unwritable.

    `jwks_fetched_at` is the "last fetch" E0-08's scope names: when the key set
    behind `jwks_url` was last retrieved. Nullable, because a platform that has
    been registered and never launched from has never been fetched, and a
    zero-value timestamp would be a lie that later code has to special-case
    anyway. `AwareDateTime` refuses a naive value at the bind boundary
    (ADR 0019).
    """

    __tablename__ = "lti_platform"
    __table_args__ = (UniqueConstraint("issuer", "client_id"),)

    # Text and not a bounded string: an issuer is a URL the platform chooses, and
    # a length limit here would reject a registration for a reason that has
    # nothing to do with Pulse. Same for the client ID, which is opaque, and for
    # the JWKS URL.
    issuer: Mapped[str] = mapped_column(Text, nullable=False)
    client_id: Mapped[str] = mapped_column(Text, nullable=False)
    jwks_url: Mapped[str] = mapped_column(Text, nullable=False)
    jwks_fetched_at: Mapped[datetime | None] = mapped_column(AwareDateTime, nullable=True)

    # **Browser horizon** (ADR 0075's per-value rule): the address a launch is
    # redirected to, resolved on the launching person's own machine and never
    # here. The development value is `http://localhost:8080/oidc/authorize`,
    # which is where a browser on the developer's host reaches the mock
    # platform — not the `mock-lms` spelling the platform's own `/registration`
    # document publishes, which is what one container reaches another by.
    #
    # **Nullable, and NULL means "not stated" rather than a default.** A
    # registration written before this column existed carries no value for it,
    # and a `NOT NULL` column would have needed a fabricated backfill; the seed's
    # idempotent re-run completes those rows. A launch from a platform whose
    # value is NULL is refused in `app.lti.launch.begin_a_launch` rather than
    # falling back to anything, because a fallback is one address standing in for
    # every registration that does not carry its own — which is the process-wide
    # setting E1-05 deletes, arriving back under another name.
    authorization_endpoint: Mapped[str | None] = mapped_column(Text, nullable=True)

    # **Tool horizon**: the platform's OAuth 2.0 token endpoint, fetched
    # server-side when this tool presents a client assertion for a service call
    # (LTI 1.3 client-credentials grant). Nullable for the same reason: a
    # registration nobody has finished stating is a different situation from one
    # stated wrongly, with a different repair. It had a second reason until
    # E1-06 — the mock platform had no token endpoint, and a registration naming
    # an address that answers nothing is a record asserting something untrue —
    # and that reason is gone: E1-06 built the endpoint and filled this column in
    # the same change, which is what the carried entry means by all four parts
    # moving together.
    auth_token_url: Mapped[str | None] = mapped_column(Text, nullable=True)


@event.listens_for(LtiPlatform, "before_insert")
@event.listens_for(LtiPlatform, "before_update")
def _judge_a_registrations_addresses(
    _mapper: Mapper[LtiPlatform], _connection: Connection, target: LtiPlatform
) -> None:
    """Put every ORM write of a registration through the address rules (ADR 0101).

    Deferred E1-05 item 3: the chokepoint above was a *call convention*, kept by
    `scripts/seed.py` because that script calls it. Nothing made the next writer
    do the same, and E11's registration console is that writer — a console that
    built the model and flushed would have been exactly as unjudged as the raw-SQL
    writer ADR 0081 records, with the difference that every test of the rules
    would still have been green, because the rules would still have been right.
    These two events are the fix: the rules fire on a writer that never called
    them, on the first write and on every edit after it. A registration is edited
    more often than it is created — a typo in a key set address, a platform
    repointed after a migration — so `before_update` is not decoration.

    **The environment comes from the session, and a session that states none is
    judged as a deployment.** The rules read `ENVIRONMENT` and an event has no
    `Settings` in hand, so the writer states where it is writing:
    `Session(info={"environment": …})`, stamped by `app.db.SessionLocal` from the
    settings it already builds its engine from, by `scripts/seed.py`, and by the
    suite's own session fixtures. Failing closed is the whole decision. Read as
    development, a writer nobody thought about registers the mock platform in
    production and nothing anywhere notices; read as a deployment, a legitimate
    development writer is refused loudly on its first run, with a message naming
    the column and a one-line repair where the session is built.

    **The default resolver, and no injection seam.** Rule 5 resolves through
    `_resolved_addresses` here, because an event has no caller to take a
    parameter from. In development it resolves nothing at all (every rule is off
    there), and in a deployment a registration write is a rare administrative act
    — this is not a hot path.

    **What is judged and what escapes, measured on SQLAlchemy 2.0.52** rather
    than assumed, because the shapes that look alike are not alike:

      - **judged** — `session.add`, an attribute changed on a row already
        persistent, and `session.merge`. Between them that is every way an
        ordinary writer, E11's console included, would write or edit a
        registration;
      - **not judged** — `Session.bulk_save_objects`, an ORM-enabled
        `session.execute(update(LtiPlatform).values(...))`, a Core `insert()`
        against the table, and raw SQL. The second of those is the one to know
        about: a bulk `UPDATE` through the ORM's own API looks exactly like a
        judged write and fires nothing, and it is a natural way to write a
        console's save.

    What bounds that residue is the grant rather than this event: `pulse_app`
    holds `SELECT` on `lti_platform` and nothing else, so a bypassing write on
    the application's own connection is refused by the database. The residue is
    a writer connecting as an identity that *may* write — the seed's bootstrap
    superuser, a migration, `psql`. ADR 0081 records the shape and ADR 0101 the
    measurement.
    """
    session = object_session(target)
    stated = session.info.get(ENVIRONMENT_SESSION_KEY) if session is not None else None
    refuse_invalid_registration_addresses(
        stated if isinstance(stated, str) else UNSTATED_ENVIRONMENT,
        authorization_endpoint=target.authorization_endpoint,
        jwks_url=target.jwks_url,
        auth_token_url=target.auth_token_url,
    )


class LtiDeployment(UuidPrimaryKey, Base):
    """One deployment of this tool within a platform (the `deployment_id` claim).

    A platform can deploy the same tool registration in more than one place — a
    sub-account, a course template — and each launch carries the deployment it
    came from. Unique per platform rather than globally: two platforms may well
    hand out the same deployment string, and it means nothing across issuers.

    Deleting a platform that still has deployments is refused rather than
    cascading, for the reason `app.models.org` gives about containment: losing the
    parent silently loses the record of what was deployed under it.
    """

    __tablename__ = "lti_deployment"
    __table_args__ = (UniqueConstraint("lti_platform_id", "deployment_id"),)

    # No index of its own: it leads `uq_lti_deployment_lti_platform_id_deployment_id`,
    # which serves a lookup of one platform's deployments.
    lti_platform_id: Mapped[UUID] = mapped_column(
        ForeignKey("lti_platform.id", ondelete="RESTRICT"), nullable=False
    )
    deployment_id: Mapped[str] = mapped_column(Text, nullable=False)


class ToolSigningKey(UuidPrimaryKey, Base):
    """This tool's own RSA private key — one row, and the tool's one identity.

    LTI 1.3 is asymmetric in both directions. `LtiPlatform` above holds where a
    *platform's* public keys are fetched from; this holds the private half of the
    key **this tool** signs with, which E1-06 spends on the `client_assertion` of
    a client-credentials grant and publishes the public half of for a platform to
    verify against.

    **Why the database rather than a setting or a file** (`docs/adr/0082`). The
    api container and the celery worker are two processes and one tool, and they
    have to sign with one key: a key generated per process gives them two, and a
    key in a per-container file gives them two the moment one is replaced. A
    platform holds the public half of exactly one of them and rejects everything
    signed by the other, with an error about a signature rather than about
    custody.

    **Only the private PEM is stored.** The public half and the RFC 7638 `kid`
    are both derived from it on read, and a stored copy of something derivable is
    a copy that can drift out of step with what it was derived from
    (`docs/MISTAKES.md` entry 19).

    **At most one row, by the same expression-index shape `institution` uses
    (ADR 0072).** A check constraint sees one row at a time and cannot count its
    own table; a unique index on a constant can, because the second row collides
    with the first and the error names this index. The index is emphatically
    *not* on `private_key_pem`: unique key material permits any number of rows
    holding *different* keys, which is precisely the state this refuses. Two rows
    is not an untidy state to reconcile later — it is two identities for one
    tool, and whichever row a process reads first decides whether its assertions
    verify.

    **`pulse_app` holds `SELECT` on this table and nothing else**, granted by
    E1-06 in `tool_signing_key_grants_v001.sql` — the ticket whose code spends
    it, which is the whole of why it did not arrive with the table: a runtime
    role holding read access to a private key it never opens is a credential at
    rest with no owner. `GET /lti/jwks` (`app.lti.registration`) is that code,
    and E1-11's `client_assertion` is the second reader. The write privileges
    stay withheld, because the seed writes this row as the superuser and an
    application connection that could write here could rotate the tool's
    identity. `RUNTIME_BASE_TABLE_PRIVILEGES` in the §4.1 suite carries the
    entry, which is where that widening has its loud conversation.

    **Not a person table.** It holds no subject, no name and no address, so
    `PERSON_TABLES` does not change — the question `docs/tickets/e1/deferred.md`
    item 2 asks of this ticket, answered.

    The key is generated by `scripts/seed.py::seed_tool_signing_key`, behind ADR
    0063's development guard. A non-development deployment has no key until the
    epic that first registers a real platform supplies one, which is a deliberate
    gap with an entry in `docs/tickets/e1/deferred.md` rather than an oversight.
    """

    __tablename__ = "tool_signing_key"
    # Named explicitly, like `uq_institution_one_row`: the `ix` template in
    # `app.models.base` interpolates a column name, and a textual expression has
    # none to give it. The migration spells the same name.
    __table_args__ = (Index("uq_tool_signing_key_one_row", text("(true)"), unique=True),)

    # PKCS#8 PEM, unencrypted. Unencrypted because the process that reads it has
    # nowhere to get a passphrase from: a passphrase in the same database is not
    # a second factor, and one in the environment moves custody back to the place
    # ADR 0082 rejects. What protects this column is the grant on it.
    private_key_pem: Mapped[str] = mapped_column(Text, nullable=False)


class LtiLaunchNonce(UuidPrimaryKey, Base):
    """A launch nonce this tool has already spent — the replay ledger (E1-08).

    A launch carries a `nonce` this tool minted at login, and a nonce is
    single-use: replaying the whole signed `id_token` a second time is the replay
    attack §9.1 names, and the signature, issuer, audience and clock are all still
    valid on the second delivery. So `app.lti.replay_guard.claim_nonce` records
    the nonce here **after every other check has passed**, with
    `INSERT ... ON CONFLICT (nonce) DO NOTHING`: the first delivery inserts and
    the launch proceeds, the second collides and is refused as
    `NonceReplayedError`. The claim rides inside the launch's own `Session`, so it
    commits with the rest of the launch or not at all.

    **Postgres rather than Redis** (ADR 0089). Every other launch-validation input
    already lives here — `LtiPlatform`, `LtiDeployment`, `ToolSigningKey` — and
    the launch already opens one `Session` the claim joins, so the unique index
    gives atomic single-use for free. Redis is the disposable task-queue broker,
    and making it the record of which credentials were already spent would pull a
    disposability-assuming component into an auth boundary. Redis's one advantage,
    native TTL, is replaced by `purge_expired_nonces` on a daily Celery beat.

    **Not a person table.** It holds a nonce, the moment it was consumed and the
    moment it expires — no subject, no name, no address — so `PERSON_TABLES` does
    not change and no identity-separated view is owed.

    **`pulse_app` holds `INSERT` and `DELETE` and nothing else**, granted by
    `lti_launch_nonce_grants_v001.sql`: `INSERT` for `claim_nonce`, which needs no
    `SELECT` because it reads single-use off the row count of the conflict, and
    `DELETE` for `purge_expired_nonces`. The write privileges are the exception a
    ledger requires — the launch door is the one path that spends a nonce — and
    the entry is recorded in `RUNTIME_BASE_TABLE_PRIVILEGES` in the §4.1 grants
    suite, where the widening has its loud conversation.
    """

    __tablename__ = "lti_launch_nonce"
    # A launch is refused by the *conflict*, so the uniqueness is on `nonce` and
    # it is the index `INSERT ... ON CONFLICT` targets. `expires_at` is indexed so
    # the daily purge deletes the expired tail without scanning the whole ledger.
    __table_args__ = (
        UniqueConstraint("nonce", name="uq_lti_launch_nonce_nonce"),
        Index("ix_lti_launch_nonce_expires_at", "expires_at"),
    )

    # The opaque `nonce` this tool minted at login and the launch echoed back.
    # Text, not a bounded string, for the same reason the issuer and client id
    # are: its length is the platform's business, not a column limit's.
    nonce: Mapped[str] = mapped_column(Text, nullable=False)
    # When the nonce was spent, defaulted to the insert moment. Recorded for
    # forensics and nothing reads it in a hot path; `AwareDateTime` refuses a
    # naive value at the bind boundary (ADR 0019).
    consumed_at: Mapped[datetime] = mapped_column(
        AwareDateTime, nullable=False, server_default=text("now()")
    )
    # When this row may be purged: the launch nonce's own lifetime, set by
    # `claim_nonce`'s caller. A row past this is dead weight the daily purge
    # removes; keeping it would refuse a *fresh* launch that happened to mint the
    # same random nonce, which is astronomically unlikely but not a reason to
    # grow the ledger without bound.
    expires_at: Mapped[datetime] = mapped_column(AwareDateTime, nullable=False)


class LtiLaunchState(UuidPrimaryKey, Base):
    """One in-flight launch handshake, held server-side between login and launch.

    A launch is two requests: `/lti/login` mints a `state` and a `nonce` and sends
    the browser to the platform, and `/lti/launch` receives the platform's signed
    answer with that `state` beside it. Something has to remember, between the two,
    that this tool started this flow and which `nonce` it is expecting back — `state`
    is the cross-site-request-forgery defence and `nonce` the injection defence, and
    both are defences only if the second request can be tied to the first.

    **This table is that memory, and it is server-side on purpose** (E1-08, ADR
    0089). E0-18 held it in a signed cookie (ADR 0078), and E1-08's first cut kept
    it in `pylti1p3`'s in-flight cookies — but a launch runs inside the LMS's
    cross-site iframe, where the browser blocks a third-party cookie *whatever its
    attributes say*, so the handshake cookie is dropped on the launch's POST and
    the launch cannot validate. SPEC §7.3 asks that "no third-party cookie is ever
    required"; keeping the handshake here rather than in a cookie is what makes that
    true. The session that a valid launch issues is already cookieless (a fragment
    the SPA captures — `app.services.session`); this finishes the other half.

    **Single-use, as a server-side property.** `app.lti.in_flight.consume_launch`
    deletes the row on a refusal, so a correct `state` replayed after a refusal
    finds nothing and is refused — the burn-after-use ADR 0078's cookie had. A row
    is *not* deleted on a successful launch: the replayed-nonce test needs the
    second delivery of a whole valid launch to reach the nonce ledger and be
    refused there as `NonceReplayedError`, and single-use of a *spent* launch is the
    nonce ledger's job (`LtiLaunchNonce`), not this table's. A successful `state`
    lingers only until its short expiry, which the daily purge reclaims.

    **Not a person table.** It holds a `state`, a `nonce` and an expiry — no
    subject, name or address — so `PERSON_TABLES` does not change and no
    identity-separated view is owed.

    **`pulse_app` holds `SELECT`, `INSERT` and `DELETE`** (`lti_launch_state_grants_v001.sql`):
    `INSERT` to remember a launch at login, `SELECT` to read the expected `nonce`
    back at launch, `DELETE` to consume it on refusal and to purge the expired tail.
    `UPDATE` stays withheld — a handshake row is written once and read once, never
    rewritten. The entry belongs in `RUNTIME_BASE_TABLE_PRIVILEGES`
    (`docs/disputes/E1-08-05.md`).
    """

    __tablename__ = "lti_launch_state"
    # The launch is looked up by the `state` the platform echoes back, so that is
    # the unique key; `expires_at` is indexed for the daily purge.
    __table_args__ = (
        UniqueConstraint("state", name="uq_lti_launch_state_state"),
        Index("ix_lti_launch_state_expires_at", "expires_at"),
    )

    # The opaque `state` this tool minted at login and the platform returns. Text
    # for the same reason the nonce is.
    state: Mapped[str] = mapped_column(Text, nullable=False)
    # The `nonce` this tool expects the launch's signed token to carry. The launch
    # reads it back here and refuses a token whose nonce is not this one.
    nonce: Mapped[str] = mapped_column(Text, nullable=False)
    # When this handshake may be purged: a few minutes, because a login a browser
    # follows completes at once. A row past this is a launch that never came back.
    expires_at: Mapped[datetime] = mapped_column(AwareDateTime, nullable=False)


class LaunchDefectKind(StrEnum):
    """Every way launch-time ingestion refuses a context (E1-10, ADR 0091, ADR 0108).

    A closed set, held as a Postgres enum type rather than as free text, for the
    reason `app.models.org`'s two enums give: the set belongs in the database
    rather than in a convention every later reader has to remember. E11 builds
    the admin surface that reads this table, and an open column would leave it
    rendering whatever string the next writer invents.

    **The member values are the wire strings and the labels in the database.**
    They are what a record says and what a hand-written `INSERT` writes, so the
    type is declared with `values_callable` rather than storing the member names
    — the two spellings would otherwise differ by case alone, which is the kind
    of difference nobody notices until a query returns nothing.
    """

    UNPARSEABLE_CONTEXT_LABEL = "unparseable_context_label"
    UNKNOWN_PREFIX = "unknown_prefix"
    OUT_OF_BAND_COURSE_NUMBER = "out_of_band_course_number"
    NO_TERM_FOR_LAUNCH_DATE = "no_term_for_launch_date"
    SECTION_CODE_UNDERIVABLE = "section_code_underivable"
    # The two E1-10's round-3 security review added. A collision is the HIGH: a
    # launch whose parsed identity names a section some *other* context is bound
    # to, which before the fix repointed that section's stored roster address and
    # rewrote its course's title. A refused address is the MEDIUM: an address the
    # registration-address rules will not let this container fetch, which leaves
    # the section provisioned and its address NULL — SPEC §7.3's never-synced
    # state, which is a state and not a fault.
    CONTEXT_COLLISION = "context_collision"
    ROSTER_ADDRESS_REFUSED = "roster_address_refused"
    # E2-02's, from the E1 boundary review's M9. §7.3's leadership limb admitted
    # any holder of a live leadership assignment with no reference to the launch's
    # context, so a Lead Faculty enrolled as a Learner in a sibling lead's course
    # could bind that section and store its roster address. The limb now checks
    # the launcher's own grant against the launched context, and this is the
    # record of a launch that did not reach it — the launch itself still lands,
    # and it is the *binding* that was refused (ADR 0108).
    CONTEXT_OUTSIDE_PURVIEW = "context_outside_purview"
    # E3-02's, and the exact mirror of `ROSTER_ADDRESS_REFUSED` above. A launch
    # advertises its AGS line-item container in the endpoint claim, the address is
    # judged by the same rules the roster address passes, and one those rules will
    # not let this container fetch leaves `section.lms_ags_line_items_url` NULL and
    # is recorded here. The launch itself still lands.
    #
    # **It is a different fact from the two states beside it**, which is why it is
    # a kind of its own rather than a second use of the roster kind. A section
    # whose platform advertised no AGS claim at all has no gradebook address and no
    # fault — SPEC §7.3's never-synced shape, applied to the gradebook — and E11's
    # surface has nothing to ask anybody to do about it. This kind says the
    # opposite: an address *was* advertised and this deployment will not call it,
    # which is a conversation with whoever configured the platform.
    AGS_ADDRESS_REFUSED = "ags_address_refused"


class LaunchDefect(UuidPrimaryKey, Base):
    """One launch whose context could not be ingested — append-only (E1-10).

    SPEC §7.3 makes a staff launch the thing that discovers a course and a
    section; §8 and ADR 0015 make an out-of-band course number "a defect to see,
    not a row to accept". A refusal that only skipped the write would leave an
    instructor looking at a product with nothing in it and nobody able to say
    why, which is `docs/MISTAKES.md` entry 26 — the fallback path swallowing the
    defect that triggered it. This row is that visibility, and E11 reads it.

    **A refusal here never fails the launch.** The person is authenticated and
    lands; it is the context that could not be read, so their `user` row is
    written and the course and section are not.

    **The field set is exactly five values beside the key, and the omissions are
    the point** (SPEC §10: no student personal information in logs). A defect is a
    fact about a *course* — which platform, which deployment, which context, when,
    and which rule fired. Never the `sub` claim, which E1-01 keeps out of every
    view and which is the join key every response in the product hangs from; never
    a name or an email; never the claims payload, which carries both. The
    enumeration is asserted as an equality in
    `tests/integration/test_launch_provisioning_defects.py`, in both directions, so
    a sixth column is a conversation rather than a commit.

    **`context_id` is nullable and the other two are not.** LTI 1.3 requires `iss`
    and the deployment claim on every launch and this tool refuses one without
    them before provisioning is reached; the context claim itself is optional, and
    a launch carrying none is an `unparseable_context_label` with nothing to name.

    **`pulse_app` holds `INSERT` and nothing else** (`launch_defect_grants_v001.sql`).
    Withholding `SELECT` keeps the read path E11's decision rather than this
    ticket's — and it shapes the writer: without `SELECT` an `INSERT ... RETURNING`
    is refused too, so the primary key is generated in Python, exactly as
    `LtiLaunchNonce` above does and for the same reason.

    **Not a person table.** No subject, no name, no address, so `PERSON_TABLES`
    does not change and no identity-separated view is owed.
    """

    __tablename__ = "launch_defect"

    # Which rule refused the launch. A record naming the wrong rule is worse than
    # no record: it is a wrong answer to the one question E11's surface exists to
    # ask, and it reads as though somebody checked.
    kind: Mapped[LaunchDefectKind] = mapped_column(
        Enum(
            LaunchDefectKind,
            name="launch_defect_kind",
            values_callable=lambda enumeration: [member.value for member in enumeration],
        ),
        nullable=False,
    )
    # The `iss` claim: which platform the launch came from. Text, as every issuer
    # in this module is — its length is the platform's business.
    issuer: Mapped[str] = mapped_column(Text, nullable=False)
    # The deployment claim: which installation of this tool inside that platform.
    # Without it a defect can only say that something went wrong somewhere.
    deployment_id: Mapped[str] = mapped_column(Text, nullable=False)
    # The context claim's `id` — the only handle E11 has on *which course* could
    # not be read. Nullable: see the class docstring.
    context_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    # When the launch was refused, defaulted to the insert moment so the writer
    # supplies nothing and no caller can record a time of its own choosing.
    # `AwareDateTime` refuses a naive value at the bind boundary (ADR 0019).
    created_at: Mapped[datetime] = mapped_column(
        AwareDateTime, nullable=False, server_default=text("now()")
    )


class NrpsCall(UuidPrimaryKey, Base):
    """One HTTP call the roster sync made to a section's NRPS service (E1-11, D9).

    SPEC §6.1 puts "NRPS and AGS call logs with response codes" on the admin
    console, and this is that log for the roster half. It is deliberately at the
    grain of an **HTTP call** and not of a sync: a roster that comes back over four
    pages is four rows, because an operator looking at a section whose sync is slow
    or partly refused needs to see which request failed, and a row per sync cannot
    say.

    **Three jobs, and the grain is load-bearing in all of them.**

      - §6.1's call log, above.
      - **The never-synced discriminator.** SPEC §7.3 makes a section with no
        stored roster address a state — "the admin console shows it as never-synced
        … rather than as empty, because a section with no roster and a section with
        no enrollments are different states and only one of them is a fault". A
        section is never-synced when it has no address *and* no rows here;
        synced-empty when it has rows here and no enrollments.
      - **The debounce's memory.** §7.3 pulls NRPS "on schedule and on launch
        (debounced)", and `app.services.roster_sync.request_section_sync` measures
        that window against this section's most recent row.

    **`response_code` is nullable and NULL has exactly one meaning: the call never
    reached the platform.** A transport failure and a refusal are different facts
    on a console — one is a network, one is a registration — so a 401 recorded as
    NULL is a tool being refused every hour that reads as an unreachable host.
    `members_seen` is nullable for the same reason: a call that failed counted
    nobody, and a zero there would be a roster that came back empty.

    **`url` is always the roster's; `response_code` is sometimes the token
    endpoint's.** A sync makes two calls to two endpoints, and when the token
    endpoint refuses, the roster is never asked at all — so there is one row, under
    the address the section's roster lives at, carrying the status the *token*
    endpoint answered. That pairing is deliberate: the row is the section's record
    of an attempted sync and §6.1's console reads it per section, so a row carrying
    an OAuth address would be a row about the platform's credential surface in the
    middle of one section's roster history. What the status is doing there is
    telling an operator that this deployment's credentials were refused while the
    platform is up — which is exactly what a NULL would hide. ADR 0095 records it.

    **Not LMS-owned, so no `guard_write` and no sanction.** SPEC §2.1's ownership
    list is courses, sections, section codes, enrollments and teaching instructors;
    this is Pulse's own record of what Pulse did, in the way `launch_defect` is.

    **Not a person table.** A section reference, a URL, an HTTP status, a count and
    a timestamp — no subject, no name, no address — so `PERSON_TABLES` does not
    change and no identity-separated view is owed. That is also the answer to
    deferred E1-01 item 2's E1-11 half: this ticket adds no person table.

    **Append-only by grant** (`roster_sync_grants_v001.sql`): `pulse_app` holds
    `SELECT` and `INSERT` here and neither `UPDATE` nor `DELETE`. E13's retention
    purge is what will trim it, on its own connection and with its own rule.
    """

    __tablename__ = "nrps_call"
    __table_args__ = (
        # **The debounce probe's own access path** (the E1 boundary review's M5).
        # `request_section_sync` asks for the newest `called_at` of one section, on
        # the request path of every staff launch, and this table grows all term
        # because nothing purges it until E13. Measured at a million rows laid out
        # hour-major: 2,006 buffers per probe against the `section_id` index alone,
        # and 5 against this one.
        #
        # `section_id` leads, because that is what the probe filters on and
        # Postgres 17 has no skip scan; `called_at` follows it, because the probe
        # then wants one end of that section's range.
        #
        # **Ascending, and E2-02 is what reversed it** (`docs/tickets/e2/carried-
        # from-e1.md`). It was `(section_id, called_at DESC)`, written as a text
        # expression because that is the only way to state a direction here — and a
        # text-expression index is not comparable, so `alembic check` read the key
        # columns as `('section_id',)` and could not see the declaration at all. The
        # gate that is supposed to catch this index being dropped, renamed or
        # re-declared was blind to it for as long as it was written that way. A
        # plain ascending composite costs the probe nothing: Postgres serves
        # `ORDER BY called_at DESC LIMIT 1` from it by a backward scan, at the same
        # 5 buffers. `d2f6a913c47e` drops the descending index and creates this one.
        #
        # **It is the only index on `section_id`, and that is deliberate.**
        # `e2c94b6a1f70` created `ix_nrps_call_section_id`; leading with the same
        # column, this one serves every lookup that one served, so keeping both
        # bought nothing and cost a second index write on every call row — of which
        # there is one per HTTP call, per section, every hour. `a4d61c8f9b27` drops
        # it in the same revision that created this index's descending predecessor,
        # and `d2f6a913c47e` swaps that one for this. That is the reasoning E0-06
        # applied to `ix_section_course_id`, and the reasoning `section`,
        # `college.institution_id`, `department.college_id` and `course.prefix_id`
        # are all left unindexed under today: an index that is merely contained by
        # another index's leading column is a write nobody reads.
        #
        # A column list rather than an expression, which is what makes this
        # declaration comparable: `alembic check` reads both key columns and holds
        # the migration to them. It is still not the whole guarantee — `check` sees
        # what is declared here against what the database has, and
        # `tests/integration/test_the_nrps_call_log_is_indexed_for_the_debounce_probe.py`
        # is what reads each key column's position and descending flag out of
        # `pg_index` on the migrated schema, and requires that no descending index
        # is left standing beside this one.
        Index("ix_nrps_call_section_id_called_at", "section_id", "called_at"),
    )

    # Which section's roster was being read. Every one of the three jobs above is
    # a query for one section's rows — the debounce most of all, which runs on a
    # staff launch while somebody waits — and the index that serves them is the
    # composite declared in `__table_args__` above, which leads with this column.
    # No `index=True` here: that would be a second index on the same leading
    # column, paid for on every insert and read by nothing. RESTRICT, matching
    # every other reference to `section` in this schema: losing a section should
    # refuse rather than silently take its call history with it.
    section_id: Mapped[UUID] = mapped_column(
        ForeignKey("section.id", ondelete="RESTRICT"), nullable=False
    )
    # The address actually called, page parameter and all — not the section's
    # stored address. A paged walk's second request is a URL the platform composed
    # in a `Link` header, and recording the stored address for all four rows would
    # lose which page failed.
    url: Mapped[str] = mapped_column(Text, nullable=False)
    # The HTTP status the platform answered with. NULL means no answer at all: see
    # the class docstring.
    response_code: Mapped[int | None] = mapped_column(nullable=True)
    # How many members this page carried. NULL for a call that failed.
    members_seen: Mapped[int | None] = mapped_column(nullable=True)
    # When the call was made. Written by the sync rather than defaulted, because
    # the debounce compares against it and the row is one of several written in a
    # single transaction — a server default would give a paged walk one timestamp
    # for every page, which is true of the transaction and not of the calls.
    # `AwareDateTime` refuses a naive value at the bind boundary (ADR 0019).
    called_at: Mapped[datetime] = mapped_column(AwareDateTime, nullable=False)


class AgsCall(UuidPrimaryKey, Base):
    """One HTTP call this tool made to a section's AGS service (E3-02).

    SPEC §6.1 puts "NRPS and AGS call logs with response codes — `nrps_call` and
    `ags_call` respectively, each at the grain of one HTTP call the tool made to a
    platform service" on the admin console, and only the NRPS half was ever built.
    This is the other half, and `NrpsCall` above is the model it is copied from
    rather than merely resembles: read that docstring first, because every piece of
    reasoning it gives about the grain and about `response_code` is repeated here
    unchanged and is not re-argued.

    **The grain is one HTTP call and not one post**, which matters more here than
    it does for the roster. Posting one score is two calls in the ordinary case —
    the token endpoint, then the score — and creating the section's line item is
    another two before either. An operator looking at a gradebook that stopped
    updating needs to see which of those failed, and a row per post cannot say.
    `grade_sync` in `app.models.grades` is the per-post record beside this one; the
    two answer different questions and neither is derivable from the other.

    **`response_code` is nullable and NULL has exactly one meaning: the call never
    reached the platform.** That is `NrpsCall`'s semantics for the same column and
    it is deliberately identical, so E11's console reads one idea rather than two.
    A transport failure and a refusal are different facts on that surface — one is
    a network, one is a registration — so a 401 recorded as NULL would be a tool
    being refused every hour that reads as an unreachable host.

    **`url` is always the AGS address; `response_code` is sometimes the token
    endpoint's**, and that pairing is `NrpsCall`'s too (ADR 0095). When the token
    endpoint refuses, the gradebook is never asked at all, so there is one row,
    under the address the call was for, carrying the status the token endpoint
    answered. A row filed under an OAuth address would be a row about the
    platform's credential surface in the middle of one section's gradebook history.

    **No count column.** `NrpsCall` carries `members_seen` because a roster page
    has a size worth recording and because "synced but empty" is a state SPEC §7.3
    names. An AGS call has no such number — a score post carries one score, and a
    container listing is walked for one line item — so nothing here would read it.
    E3-04 and E3-06 are the tickets that make the calls, and a column added now for
    them to fill is a column added before anybody knows what would go in it.

    **Not LMS-owned, so no `guard_write` and no sanction.** SPEC §2.1's ownership
    list is courses, sections, section codes, enrollments and teaching instructors;
    this is Pulse's own record of what Pulse did, exactly as `nrps_call` and
    `launch_defect` are.

    **Not a person table.** A section reference, a URL, an HTTP status and a
    timestamp — no subject, no name, no address, and no reference to any table that
    holds one — so `PERSON_TABLES` does not change and no identity-separated view
    is owed. The person walk in
    `tests/integration/test_identity_column_marker.py` does not reach it at all.

    **Append-only by grant** (`grade_passback_grants_v001.sql`): `pulse_app` holds
    `SELECT` and `INSERT` here and neither `UPDATE` nor `DELETE`. E13's retention
    purge is what will trim it, on its own connection and with its own rule.

    **No index beyond the primary key's, and that is a decision.** `NrpsCall`
    carries a composite because the debounce probe reads it on the request path of
    every staff launch, measured at 2,006 buffers against 5. Nothing reads this
    table on a request path: E11's console is the only reader SPEC §6.1 names, it
    is not built, and an index maintained on every insert for a query nobody runs
    is a write nobody reads. E11 adds one when it knows its own access path.
    """

    __tablename__ = "ags_call"

    # Which section's gradebook the call was about. RESTRICT, matching every other
    # reference to `section` in this schema: losing a section should refuse rather
    # than silently take its call history with it. No `index=True` — see the class
    # docstring for why this table carries no index of its own yet.
    section_id: Mapped[UUID] = mapped_column(
        ForeignKey("section.id", ondelete="RESTRICT"), nullable=False
    )
    # The address actually called — the container, a line item, or the token
    # endpoint when that is what refused. Not the section's stored address: a line
    # item's own id is a different URL from the container it lives in, and
    # recording the stored one would lose which of the two failed.
    url: Mapped[str] = mapped_column(Text, nullable=False)
    # The HTTP status the platform answered with. NULL means no answer at all: see
    # the class docstring.
    response_code: Mapped[int | None] = mapped_column(nullable=True)
    # When the call was made. Written by the caller rather than defaulted, for
    # `NrpsCall`'s reason: several calls are written in one transaction and a
    # server default would give them all one timestamp, which is true of the
    # transaction and not of the calls. `AwareDateTime` refuses a naive value at
    # the bind boundary (ADR 0019).
    called_at: Mapped[datetime] = mapped_column(AwareDateTime, nullable=False)
