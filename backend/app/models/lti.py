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
from datetime import datetime
from enum import StrEnum
from urllib.parse import urlsplit
from uuid import UUID

from sqlalchemy import Enum, ForeignKey, Index, Text, UniqueConstraint, text
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

# The three this container fetches, as opposed to the one it hands to a browser.
# Rules 3 and 4 below are the whole of that distinction.
FETCHED_COLUMNS = (JWKS_URL_COLUMN, AUTH_TOKEN_URL_COLUMN, ROSTER_SERVICE_ADDRESS_COLUMN)

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
LOOPBACK_REFUSED_COLUMNS = (AUTHORIZATION_ENDPOINT_COLUMN, ROSTER_SERVICE_ADDRESS_COLUMN)


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

    The chokepoint every writer of an `lti_platform` row is expected to call —
    today `scripts/seed.py` does, and E11's registration console must. **A call
    convention, not an enforcement point**: no mapper event or sweep makes a
    future writer call it, which this ticket's security review recorded and
    `docs/tickets/e1/deferred.md` carries with a done-when. E0-24 item 1 left
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
        _refuse_an_unacceptable_address(column, value)


def refuse_invalid_fetched_address(environment: str, *, column: str, address: str | None) -> None:
    """Judge one address this container fetches, by the rules above and no others.

    E1-10's roster service address (`section.lms_context_memberships_url`) is the
    third address in this system that this container fetches: it arrives on a
    launch as an NRPS claim, and E1-11 calls it with the tool's own client
    credentials, on a schedule, with nobody present. It is not a registration
    column, so `refuse_invalid_registration_addresses` above cannot judge it — and
    a second copy of the rules would be `docs/MISTAKES.md` entry 13, a hazard
    worked around in one of the two places facing it. So both callers reach the
    same four rules through `_refuse_an_unacceptable_address`, and this one
    exists to supply the two things that function cannot infer: the environment
    gate, and that `None` is "not stated" rather than a value to judge.

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
    """
    if not is_a_deployment(environment) or address is None:
        return
    _refuse_an_unacceptable_address(column, address)


def _refuse_an_unacceptable_address(column: str, value: str) -> None:
    """The four rules, applied to one stated address. See the two callers above.

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
    """The five ways launch-time ingestion refuses a context (E1-10, ADR 0091).

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

    # Which section's roster was being read. Indexed, because every one of the
    # three jobs above is a query for one section's rows — the debounce most of
    # all, which runs on a staff launch while somebody waits. RESTRICT, matching
    # every other reference to `section` in this schema: losing a section should
    # refuse rather than silently take its call history with it.
    section_id: Mapped[UUID] = mapped_column(
        ForeignKey("section.id", ondelete="RESTRICT"), nullable=False, index=True
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
