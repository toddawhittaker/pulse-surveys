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

**What a legitimate address is, is decided here too** (`docs/adr/0081`).
`refuse_invalid_registration_addresses` below is the chokepoint every writer of
an `lti_platform` row passes through. E0-24 item 1 left `jwks_url`
credential-equivalent and unconstrained — it decides which keys may sign an
accepted launch, and it is fetched server-side on every launch — and E1 is the
epic that writes and fetches it, so E1 says what it may hold.

**Nothing here is marked LMS-owned.** An `lms_` prefix (ADR 0014) marks a column
Pulse may never edit. A registration is typed into the admin console by an
administrator (SPEC §2, Admin: "LTI registration"), so every column in this
module is Pulse's to write. `user.lms_user_id` in `app.models.identity` is the
contrasting case: the `sub` claim arrives from the platform and Pulse never
chooses it.
"""

import ipaddress
from datetime import datetime
from urllib.parse import urlsplit
from uuid import UUID

from sqlalchemy import ForeignKey, Index, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

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
    "LtiDeployment",
    "LtiPlatform",
    "RegistrationAddressError",
    "ToolSigningKey",
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

# The two this container fetches on every launch, as opposed to the one it hands
# to a browser. Rules 3 and 4 below are the whole of that distinction.
FETCHED_COLUMNS = (JWKS_URL_COLUMN, AUTH_TOKEN_URL_COLUMN)


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


def refuse_invalid_registration_addresses(
    environment: str,
    *,
    authorization_endpoint: str | None,
    jwks_url: str,
    auth_token_url: str | None,
) -> None:
    """Refuse a registration whose addresses this environment will not accept.

    The one chokepoint every writer of an `lti_platform` row passes through —
    today `scripts/seed.py`, later E11's registration console. E0-24 item 1 left
    `jwks_url` credential-equivalent and unconstrained, and E1 writes and fetches
    it, so E1 says what a legitimate value looks like. `docs/adr/0081` is this
    ticket's own decision and states where ADR 0077's vocabulary carries over and
    where it deliberately differs.

    **A validator rather than a `CHECK` constraint**, because every rule reads
    `ENVIRONMENT` and the database does not hold it. The residue is that a writer
    going round SQLAlchemy is not judged at all; that is the same accepted
    posture ADR 0068's guard has, and ADR 0081 records it rather than hiding it.

    **NULL passes.** Both new columns are nullable and absence means "not
    stated", never a default. A NULL `authorization_endpoint` is refused at the
    *launch* (`app.lti.launch.begin_a_launch`), not at the write.

    Four rules, all of them switched off where `environment` is exactly the
    development name — the mock's own addresses have to seed, and a rule that
    kept firing there would meet a developer as an unexplained refusal from
    `make seed`:

      1. **https**, with the on-this-machine exemption ADR 0077 rule 4 carries:
         a cleartext sidecar addressed by loopback stays deployable.
      2. **The mock platform's host is refused** on all three columns.
      3. **Loopback is refused on `authorization_endpoint`**, as a class, and on
         no other column. That string is resolved on the *reader's* machine, so
         loopback there is the launching person's own computer; the two fetched
         columns are resolved here, where a sidecar is an ordinary deployment.
      4. **Link-local is refused on the two fetched columns.** They are the only
         addresses a stored row makes this container fetch, the cloud metadata
         service lives at `169.254.169.254`, and no legitimate LMS does.
         **Private ranges are accepted everywhere**: an institution running its
         LMS on `10.0.0.5` behind its own network is an ordinary deployment, and
         `not ip.is_global` would sweep that up with the metadata service.

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
    for column, value in addresses.items():
        if value is None:
            continue
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

        if column == AUTHORIZATION_ENDPOINT_COLUMN and is_a_loopback_host(host):
            raise RegistrationAddressError(
                f"The registration's `{column}` names this machine — localhost or a loopback "
                "address. A browser, not this container, is what resolves it, so loopback there is "
                "the launching person's own computer, and whatever listens on that port receives "
                "an authorization request arriving from a Pulse URL. Register the platform's own "
                "browser-facing address, or run with ENVIRONMENT=development."
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
    # (LTI 1.3 client-credentials grant). Nullable for the same reason and with a
    # second one of its own — the mock platform has no token endpoint until
    # E1-06 builds it, and a registration naming an address that answers nothing
    # is a record asserting something untrue. E1-06 fills it in the change that
    # creates the endpoint.
    auth_token_url: Mapped[str | None] = mapped_column(Text, nullable=True)


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

    **Nothing reads this table yet, and no `pulse_app` grant exists for it.**
    E1-06 signs with the key, and the grant lands there with the code that spends
    it: a runtime role holding read access to a private key it never opens is a
    credential at rest with no owner. `RUNTIME_BASE_TABLE_PRIVILEGES` in the
    §4.1 suite compares privileges *held*, so a table granted nothing contributes
    no entry and the equality is unchanged here on purpose.

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
