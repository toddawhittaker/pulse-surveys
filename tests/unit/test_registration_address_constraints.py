"""What a legitimate registration address looks like — ticket E1-05, criterion 3.

E0-24 item 1 left `jwks_url` credential-equivalent and unconstrained: it decides
which keys may sign an accepted launch, it is fetched server-side on every
launch, and until this ticket any string at all could be written into it. E1-05
adds two more columns beside it — the platform's browser-facing
`authorization_endpoint` and its tool-facing `auth_token_url` — and fixes the
floor for all three at one chokepoint.

**The subject is one function**, `app.models.lti.refuse_invalid_registration_addresses`,
called by every writer of an `lti_platform` row. It takes the environment name
and the three addresses and either returns or raises
`app.models.lti.RegistrationAddressError`. Nothing here reaches the database:
the rules read `ENVIRONMENT`, which the database does not hold, which is why the
chokepoint is a validator and not a `CHECK` constraint.

**Four rules, and every one of them is asserted from both sides.** A validator
that refuses everything outside development passes every refusal test in this
module and makes Pulse undeployable; a validator that refuses nothing in
development passes them too and stops the demo seed writing the mock's own
addresses. The acceptance rows are what tell those two apart from the right one,
and the sharpest of them is
`test_the_registration_the_seed_writes_is_accepted_in_development` — the row
`scripts/seed.py` writes is the whole of E0's launchable-into system.

  1. **https**, outside development, with the same on-this-machine loopback
     exemption `ai_provider_base_url` and ADR 0077 rule 4 already carry.
  2. **The mock platform's host is refused** on all three columns outside
     development, with ADR 0077's one-trailing-dot strip.
  3. **Loopback is refused on `authorization_endpoint` only**, as a class rather
     than as a list of spellings, and stays legal on the two columns this
     container fetches — a provider or platform sidecar is an ordinary
     deployment. That split is ADR 0077's, for the reason it gives: the
     browser-facing string is resolved on the reader's machine and the other two
     are resolved here.
  4. **Link-local is refused on `jwks_url` and `auth_token_url`**, which are the
     two fetched server-side on every launch, because the cloud metadata service
     lives at `169.254.169.254` and no legitimate LMS does. **Private ranges are
     accepted everywhere**: an institution's LMS on `10.0.0.5` is an ordinary
     deployment, and that pair — link-local refused, private accepted — is the
     near miss this rule stands or falls on.

**A NULL passes.** Both new columns are nullable and NULL means "not stated",
never a default: the launch door refuses a registration whose
`authorization_endpoint` is NULL rather than falling back to anything, which is
`tests/integration/test_registration_endpoints_are_per_platform.py`'s subject.
Here, absence is simply not an address and there is nothing to judge about it.

**What this module deliberately does not decide.** The ticket's rules say nothing
about a link-local `authorization_endpoint`, and nothing here asserts that such a
value is refused or that it is accepted. It is a browser-facing string, so the
argument that closes rule 4 (this container fetches it) does not reach it; making
up an answer here would settle a question the ticket leaves open, in a test, on
the implementer's behalf.

**Every refusal is written so that exactly one rule can be what fires.** The
mock, loopback and link-local rows all carry `https`, so the transport rule
cannot be what refuses them; where two rules genuinely overlap there is a test
that says so by name. A refusal that passes because a neighbouring rule fired is
green for a reason unrelated to what it asserts (`docs/MISTAKES.md` entry 3), and
with four rules over three columns that is this module's most likely failure
rather than a hypothetical.

**Which failure a red here is.** Everything except the four control tests at the
end is expected red on the current tree, on the named absence of
`refuse_invalid_registration_addresses` or `RegistrationAddressError` — reported
as a failed assertion naming the symbol rather than as a collection error, which
is what `refuse_addresses` and `registration_error` below are for. The controls
must be green today: they are arithmetic on this module's own constants and on
fixtures that already exist, and a red one means these tests are broken rather
than that the code is.

ADR 0077's own refusal tests, in `tests/unit/test_oidc_provider_configuration.py`,
are untouched by this ticket and must keep passing. This module borrows that
one's vocabulary where the question is the same and says where it differs; the
ticket requires the decision itself to be E1-05's own, in its own ADR.
"""

from collections.abc import Mapping
from typing import Any

import pytest

# The three columns the chokepoint judges, spelled as the keyword arguments the
# function takes. **Not this module's choice**: E1-05 names `jwks_url` (E0-08
# created it), and the two new columns are named by the ticket and by the mock's
# `/registration` document, whose keys are the column names.
AUTHORIZATION_ENDPOINT = "authorization_endpoint"
JWKS_URL = "jwks_url"
AUTH_TOKEN_URL = "auth_token_url"  # noqa: S105 - a column name, not a credential

# The two columns this container fetches on every launch, and the one it hands to
# a browser. The split is the whole of rules 3 and 4, so it is written down once
# here rather than re-derived in each test.
FETCHED_COLUMNS = (JWKS_URL, AUTH_TOKEN_URL)
EVERY_COLUMN = (AUTHORIZATION_ENDPOINT, JWKS_URL, AUTH_TOKEN_URL)

# The two columns that may be NULL. `jwks_url` is not among them: a registration
# with no key set address is one whose launches cannot be verified at all, and
# the function's own signature takes it as a `str`.
NULLABLE_COLUMNS = (AUTHORIZATION_ENDPOINT, AUTH_TOKEN_URL)

# The Compose service name the mock platform runs as, written out rather than
# derived for the reason ADR 0077's catalog is: a two-entry rule that a reviewed
# diff should have to change. Held against reality by a control at the end of
# this module — a catalog naming a service nothing runs under refuses nothing and
# reports every registration clean (`docs/MISTAKES.md` entry 35).
MOCK_SERVICE = "mock-lms"

# A real institution's platform, and the background of every test here. Every row
# that asks about one bad value sets the other two from this, so that a refusal
# fired by a neighbouring value cannot read as the rule under test firing
# (`docs/MISTAKES.md` entry 3). `.example.edu` resolves nowhere and nothing here
# is fetched.
DEPLOYED_HOST = "lms.example.edu"
DEPLOYED_REGISTRATION = {
    AUTHORIZATION_ENDPOINT: f"https://{DEPLOYED_HOST}/lti/authorize",
    JWKS_URL: f"https://{DEPLOYED_HOST}/.well-known/jwks.json",
    AUTH_TOKEN_URL: f"https://{DEPLOYED_HOST}/lti/token",
}

# The registration `scripts/seed.py` writes for the mock, which every one of
# these rules has to accept in development or the demo stack stops seeding. The
# key set URL is ADR 0068's literal, the authorization endpoint is E1-05's
# development value, and the token endpoint is E1-06's — it was NULL while the
# mock had no token endpoint, and it names one now that the mock serves one.
#
# **That third value is what makes this the sharpest row in the module.** It is
# cleartext, on the mock's own Compose service name, which rules 1 and 2 both
# refuse outside development — so a validator missing either environment
# condition stops `make seed`, and with it E0's exit criterion.
DEVELOPMENT_REGISTRATION = {
    AUTHORIZATION_ENDPOINT: "http://localhost:8080/oidc/authorize",
    JWKS_URL: f"http://{MOCK_SERVICE}:8000/.well-known/jwks.json",
    AUTH_TOKEN_URL: f"http://{MOCK_SERVICE}:8000/token",
}

# Environments that are not the development one, as templates: the development
# name is read from `app.config` rather than spelled here, and parametrisation
# needs a value at collection time. The last two rows are the near miss that
# matters — a rule written as `DEVELOPMENT in environment` passes every other row
# and hands `staging-development` the mock, which is exactly the shape
# `tests/integration/test_demo_seed_script.py` carries against the seed's gate.
NON_DEVELOPMENT_ENVIRONMENTS = (
    "production",
    "staging",
    "{development}-blue",
    "pre-{development}",
)

# Fewer rows where the question is not "which names count as a deployment": that
# is settled once, by the mock-catalog test, and repeating it under every rule
# below would be copies of one assertion rather than more assertions.
DEPLOYMENT_ENVIRONMENTS = ("production", "staging")

# Mock addresses, one per spelling, because a rule that matches the development
# stack's exact string is not a rule about the host. The port, the scheme and the
# path are not the question — a container reaching `mock-lms` on any port reaches
# the mock — and every row carries TLS so that the transport rule cannot be what
# refuses it.
MOCK_URL_SPELLINGS = {
    "no port": f"https://{MOCK_SERVICE}/lti/token",
    "https on another port": f"https://{MOCK_SERVICE}:8443/lti/token",
    "no path": f"https://{MOCK_SERVICE}:8000",
    "a query string": f"https://{MOCK_SERVICE}:8000/lti/token?tenant=1",
    "upper case": f"https://{MOCK_SERVICE.upper()}:8443/lti/token",
}

# One trailing dot, which is how `mock-lms.` reaches the mock exactly as
# `mock-lms` does. Exactly one: stripping more, or comparing by prefix, would
# turn the subdomain row below into a refusal (ADR 0077).
MOCK_URL_WITH_A_TRAILING_DOT = f"https://{MOCK_SERVICE}.:8443/lti/token"

# The other direction: addresses that contain the service name and do not resolve
# to it. Each is a real address an institution could hold, and each is refused by
# the substring rule that is the obvious way to write the catalog.
NON_MOCK_URL_SPELLINGS = {
    "the service name as a subdomain": f"https://{MOCK_SERVICE}.example.edu/lti/token",
    "a host the service name prefixes": f"https://{MOCK_SERVICE}-2.example.edu/lti/token",
    "a host the service name ends": f"https://staging-{MOCK_SERVICE}/lti/token",
    "the service name in the path": f"https://{DEPLOYED_HOST}/{MOCK_SERVICE}/lti/token",
}

# **Loopback is a class, not a list of spellings**, and the extra two rows are
# the point. A catalog of `localhost`, `127.0.0.1` and `::1` is walked past by
# `127.0.0.2` — an ordinary address in `127.0.0.0/8`, every one of which is the
# local machine — and by the IPv4-mapped form, which reads as loopback on this
# repository's interpreter and matches no spelling. ADR 0077's own finding
# arrived with the fourth spelling already in it, and E1-01's battery lesson is
# that a closed-set guard is defeated one level further out each round.
#
# Spelled as they appear in a URL: an IPv6 literal is bracketed there and bare in
# `urlsplit(...).hostname`.
LOOPBACK_URL_HOSTS = {
    "the name": "localhost",
    "the usual address": "127.0.0.1",
    "another address in 127.0.0.0/8": "127.0.0.2",
    "the IPv6 literal": "[::1]",
    "the IPv4-mapped IPv6 literal": "[::ffff:127.0.0.1]",
}

# The two link-local families rule 4 refuses on the fetched columns. The first is
# the address the rule exists for: the cloud metadata service, reachable from
# inside a container on most providers, answering credentials to anything that
# asks. The second is the IPv6 half, included because a rule written over
# `169.254.0.0/16` alone leaves it.
LINK_LOCAL_URL_HOSTS = {
    "the cloud metadata service": "169.254.169.254",
    "another address in 169.254.0.0/16": "169.254.0.1",
    "the IPv6 link-local literal": "[fe80::1]",
}

# Private ranges, which are **accepted**, and are the near miss that keeps rule 4
# honest: an institution running its LMS on RFC 1918 space, or on an IPv6 unique
# local address, is an ordinary deployment and the cheapest way to satisfy every
# link-local refusal above is to refuse every non-public address.
PRIVATE_URL_HOSTS = {
    "RFC 1918": "10.0.0.5",
    "the other RFC 1918 block": "192.168.10.4",
    "an IPv6 unique local address": "[fd00::5]",
}

# An address that is emphatically neither loopback nor private nor link-local, so
# that "an IP literal" cannot stand in for any of the three classes. TEST-NET-3
# (RFC 5737) is reserved for documentation and names nobody's real host.
NON_LOOPBACK_IP_LITERAL = "203.0.113.10"

# The offending value the refusal-message tests use. The path and query are
# distinctive so that "the message does not quote the value" is a statement about
# this string rather than about a substring that could appear by accident.
OFFENDING_MOCK_URL = f"https://{MOCK_SERVICE}:8443/lti/token?tenant=e1-05-registration"
OFFENDING_DETAIL = "tenant=e1-05-registration"


def refuse_addresses() -> Any:
    """The chokepoint, imported inside the test so a missing one fails loudly.

    Imported here rather than at module scope for the reason
    `tests/unit/test_oidc_provider_configuration.py` gives about `Settings`: an
    `ImportError` at collection is a broken module rather than a red test, and
    the two are fixed by different people. What comes out of this on the current
    tree is a failed assertion naming the symbol E1-05 is asked to add.
    """
    try:
        from app.models.lti import refuse_invalid_registration_addresses
    except ImportError as absent:
        pytest.fail(
            "`app.models.lti` exposes no `refuse_invalid_registration_addresses` "
            f"({absent}). E1-05 puts the registration-address rules at one chokepoint in that "
            "module, called by every writer of an `lti_platform` row — today that is "
            "`scripts/seed.py` and later E11's registration console. Until it exists every "
            "assertion in this file is about a function that is not there."
        )
    return refuse_invalid_registration_addresses


def registration_error() -> type[BaseException]:
    """The error the chokepoint raises, named rather than caught as `Exception`.

    Named for the reason `test_ai_provider_configuration.py` gives on the same
    import: a bare `Exception` is satisfied by an `AttributeError` out of a
    renamed symbol, which is a broken test reading as a refused registration —
    the exact inversion this suite exists to prevent.
    """
    try:
        from app.models.lti import RegistrationAddressError
    except ImportError as absent:
        pytest.fail(
            f"`app.models.lti` exposes no `RegistrationAddressError` ({absent}). E1-05 raises it "
            "from the registration-address chokepoint, and a refusal test that caught anything "
            "else would pass on a `TypeError` from calling a function that does not exist."
        )
    return RegistrationAddressError


def development_environment() -> str:
    """The `ENVIRONMENT` value that means development, read from its one definition.

    Out of `app.config` rather than written here, because E0-37 item 2 made that
    constant the single definition site and a literal in this module would be one
    more copy of the value that item exists to remove.
    """
    from app.config import DEVELOPMENT_ENVIRONMENT

    assert isinstance(DEVELOPMENT_ENVIRONMENT, str) and DEVELOPMENT_ENVIRONMENT, (
        "`app.config.DEVELOPMENT_ENVIRONMENT` is not a non-empty string, so this module cannot "
        "tell which environment the mock's own addresses are permitted in."
    )
    return DEVELOPMENT_ENVIRONMENT


def environment_named(template: str) -> str:
    """One row of `NON_DEVELOPMENT_ENVIRONMENTS`, with the development name filled in."""
    name = template.format(development=development_environment())
    assert name != development_environment(), (
        f"The environment row {template!r} resolves to the development environment itself, so a "
        "test using it would be asserting the development case under a deployment's name."
    )
    return name


def registration(**overrides: str | None) -> dict[str, str | None]:
    """A real institution's three addresses, with `overrides` applied.

    Every test builds its case this way rather than leaving the other two columns
    unset, so that the value under test is the only thing a refusal could be
    about.
    """
    values: dict[str, str | None] = dict(DEPLOYED_REGISTRATION)
    values.update(overrides)
    return values


def judge(environment: str, addresses: Mapping[str, str | None]) -> None:
    """Put one registration through the chokepoint under one environment name."""
    refuse_addresses()(environment, **dict(addresses))


# ---------------------------------------------------------------------------
# Rule 1 — https outside development, with the on-this-machine exemption.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("environment", DEPLOYMENT_ENVIRONMENTS)
@pytest.mark.parametrize("column", EVERY_COLUMN)
def test_a_cleartext_address_off_this_machine_is_refused_outside_development(
    column: str, environment: str
) -> None:
    """Cleartext to another host is refused on every column.

    All three, because each is cleartext in a different way and a rule covering
    some of them would read as covering the registration. `jwks_url` is fetched
    to decide which keys may sign an accepted launch, so anyone on the path can
    answer with a key set of their own and every launch they then sign verifies
    correctly — the signing oracle ADR 0077 closed for the web door, arriving
    here through a database column instead of a setting. `auth_token_url` is
    where the tool presents its own client assertion. `authorization_endpoint` is
    a URL a browser is sent to, and cleartext there puts the authorization
    request and its `state` on the wire.

    **The mutation this kills:** no transport rule at all, which is the state at
    HEAD; and a transport rule applied to the fetched pair only.

    **The near misses that must stay green:** cleartext in development, which is
    the whole demo stack and is asserted below, and cleartext to this machine,
    which is a sidecar and is the test after next.
    """
    with pytest.raises(registration_error()):
        judge(
            environment_named(environment),
            registration(**{column: f"http://{DEPLOYED_HOST}/lti/token"}),
        )


@pytest.mark.parametrize("column", EVERY_COLUMN)
def test_a_cleartext_address_is_accepted_in_development(column: str) -> None:
    """The pair: the same value, one environment name different.

    Every address on the development stack is cleartext to another container —
    `http://mock-lms:8000` — so an unconditional transport rule refuses the
    registration `scripts/seed.py` writes and takes SPEC §14.3's exit criterion
    with it. This is the row that says the rule reads `ENVIRONMENT`.

    **The mutation this kills:** the transport rule written without the
    environment condition, which passes every refusal row above.
    """
    judge(
        development_environment(),
        registration(**{column: f"http://{DEPLOYED_HOST}/lti/token"}),
    )


@pytest.mark.parametrize("host", list(LOOPBACK_URL_HOSTS.values()))
@pytest.mark.parametrize("column", FETCHED_COLUMNS)
def test_a_cleartext_fetched_address_on_this_machine_is_accepted_outside_development(
    column: str, host: str
) -> None:
    """The exemption ADR 0077 rule 4 already carries, on the two columns it reaches.

    A platform or a key-set sidecar running beside the application is reached by
    this container at a loopback address, and its transport may legitimately be
    plain `http` there: the packet never leaves the machine. ADR 0077 names this
    shape in its consequences and this ticket keeps it, so the refusal above has
    to stop at the boundary rather than at every `http`.

    **The mutation this kills:** an absolute transport rule, which refuses a
    supported deployment while protecting nothing. **Its pair** is the first test
    in this module, where the identical scheme to another host is refused.
    """
    judge(
        "production",
        registration(**{column: f"http://{host}:8443/lti/token"}),
    )


# ---------------------------------------------------------------------------
# Rule 2 — the mock platform's host, refused outside development on all three.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("environment", NON_DEVELOPMENT_ENVIRONMENTS)
@pytest.mark.parametrize("column", EVERY_COLUMN)
def test_a_mock_address_is_refused_on_every_column_outside_development(
    column: str, environment: str
) -> None:
    """A registration naming the in-repo mock is refused wherever this is not development.

    `mock-lms` authenticates nobody: it signs a launch as whatever subject the
    caller picks, and ADR 0038's fourth property — that a production Pulse holds
    no row naming that issuer — is what makes shipping it in the base Compose
    file survivable. ADR 0068 moved that boundary from "no such row exists in
    this repository" to "no run permitted to write it can start", and this rule
    is the third layer: a row naming the mock is refused at the write even where
    a guard was bypassed.

    Four environment names, because the two obvious one-line conditions each pass
    some rows and fail others: `environment == "production"` lets staging trust
    the mock, and `DEVELOPMENT in environment` lets anything named after
    development trust it.

    **The mutation this kills:** no catalog at all, and a catalog applied to
    `jwks_url` only — which is the column E0-24 item 1 named, so a rule written
    from that sentence alone covers one of three.

    **The value carries TLS**, so the transport rule cannot be what refuses it
    and a green row cannot be misattributed.
    """
    with pytest.raises(registration_error()):
        judge(
            environment_named(environment),
            registration(**{column: f"https://{MOCK_SERVICE}:8443/lti/token"}),
        )


@pytest.mark.parametrize("spelling", list(MOCK_URL_SPELLINGS))
def test_the_mock_host_is_refused_however_the_address_is_spelled(spelling: str) -> None:
    """The rule is about the host, so the port, the scheme, the path and the case do not excuse it.

    A container on this network reaches the mock at `mock-lms` on whatever port
    it listens on, so a rule written against `http://mock-lms:8000/...` — the
    exact string ADR 0068 seeds, and the obvious thing to compare — is defeated
    by an operator who copies the address and changes the port, or who terminates
    TLS in front of it. Host names are case-insensitive (RFC 4343) and Compose
    folds nothing, so `MOCK-LMS` resolves exactly as the lower-case spelling
    does.

    **The mutation this kills:** equality against the seeded URL, or against
    `host:port`, or `netloc.split(":")[0]`, which does not fold case, as against
    `urlsplit(url).hostname`, which does.
    """
    with pytest.raises(registration_error()):
        judge("production", registration(**{JWKS_URL: MOCK_URL_SPELLINGS[spelling]}))


def test_the_mock_host_is_refused_with_one_trailing_dot() -> None:
    """`mock-lms.` reaches the mock, so a catalog comparing strings is defeated by one character.

    ADR 0077 solved this once for the identity provider and the solution is a
    parsing quirk rather than a rule — which is exactly the shape
    `docs/MISTAKES.md` entry 13 is about, a hazard worked around in one of the
    two places facing it. E1-05 faces it in the second place, and the ticket says
    to route through the helper that already answers this question rather than to
    re-derive the parsing.

    **The mutation this kills:** the strip omitted. **Its pair** is the subdomain
    row below: stripping more than one dot, or comparing by prefix afterwards,
    turns `mock-lms.example.edu.` into a refusal.
    """
    with pytest.raises(registration_error()):
        judge("production", registration(**{JWKS_URL: MOCK_URL_WITH_A_TRAILING_DOT}))


@pytest.mark.parametrize("spelling", list(NON_MOCK_URL_SPELLINGS))
def test_an_address_that_merely_contains_the_service_name_is_accepted(spelling: str) -> None:
    """The host is compared as a component, not searched for as a substring.

    Each row is an address a real institution could hold, and each is refused by
    the one-line version of this rule — `"mock-lms" in url` — that the refusals
    above cannot tell from the right one. A subdomain, a host the name prefixes,
    a host the name ends, and a path segment: none of them resolves to the
    Compose service, which is the only thing the catalog names.

    **The mutation this kills:** substring matching, over the URL or over the
    host. **The near miss on the other side:** `MOCK_URL_SPELLINGS` above, where
    the host is exactly the service name and every row is refused.
    """
    judge("production", registration(**{JWKS_URL: NON_MOCK_URL_SPELLINGS[spelling]}))


def test_the_registration_the_seed_writes_is_accepted_in_development() -> None:
    """The row `scripts/seed.py` writes for the mock, judged where it is written.

    The sharpest acceptance in the module. Every rule above is satisfied by a
    validator that raises whenever any address names the mock or carries no TLS,
    and such a validator stops `make seed` from writing the registration that
    makes the development stack launchable at all — which is E0's exit criterion
    and the thing E1 is built on top of.

    All three values at once, because that is how the seed calls it: the mock's
    cleartext key set on a Compose service name, the browser-facing endpoint on
    loopback where a developer's browser reaches the platform, and — since E1-06
    gave the mock a token endpoint — a cleartext `auth_token_url` on that same
    Compose service name.

    **That third value sharpened this test rather than changing its subject.**
    While it was NULL it exercised nothing: NULL passes every rule by decision.
    Now it is an address rules 1 and 2 both refuse outside development, so this
    row is refused by any validator that lost either environment condition.

    **The mutation this kills:** any of the four rules written without its
    environment condition.
    """
    judge(development_environment(), DEVELOPMENT_REGISTRATION)


@pytest.mark.parametrize("environment", NON_DEVELOPMENT_ENVIRONMENTS)
def test_a_real_institutions_registration_is_accepted_outside_development(
    environment: str,
) -> None:
    """The point of the whole rule: a real LMS registered in a real deployment works.

    Every refusal in this module is satisfied by a chokepoint that raises
    whenever `ENVIRONMENT` is not the development name, which would make Pulse
    registrable nowhere. This is the row that says the rules are about the
    addresses rather than about deployments.

    **A red here today means these tests are broken, not the code:** no validator
    exists yet, so what this asserts before the ticket lands is that
    `DEPLOYED_REGISTRATION` is a registration the chokepoint accepts — the
    background every refusal above is measured against.
    """
    judge(environment_named(environment), registration())


# ---------------------------------------------------------------------------
# Rule 3 — loopback, refused on the browser-facing column and on no other.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("environment", DEPLOYMENT_ENVIRONMENTS)
@pytest.mark.parametrize("spelling", list(LOOPBACK_URL_HOSTS))
def test_a_loopback_authorization_endpoint_is_refused_outside_development(
    spelling: str, environment: str
) -> None:
    """The browser-facing endpoint may not point at the end user's own machine.

    This column is never resolved in this container: it is a string handed to a
    browser and resolved on the machine that browser is running on. A deployment
    that registered a platform with `http://localhost:8080/oidc/authorize` — the
    development value, and the value an operator copies forward — answers every
    launch with a redirect to a port on the launching person's own computer,
    where anything listening receives an institution-issued link arriving from a
    Pulse URL and can render a login page of its own.

    **Five spellings, because the rule is a class.** `[::1]` is what a machine
    with IPv6 resolves `localhost` to first, `127.0.0.2` is an ordinary address
    in `127.0.0.0/8`, and `::ffff:127.0.0.1` is the IPv4-mapped form that matches
    no written-out spelling at all.

    **The one-level-out mutation this kills:** the rule written as the three
    literal spellings `localhost`, `127.0.0.1` and `[::1]`. That passes the
    first, second and fourth rows and must go red on `127.0.0.2` and on
    `[::ffff:127.0.0.1]`.

    **https, deliberately**, so the transport rule cannot be what refuses these.
    **The near misses that must stay green:** the same values in development, the
    same hosts on the two fetched columns, and a non-loopback IP literal on this
    same column — all three are below.
    """
    with pytest.raises(registration_error()):
        judge(
            environment_named(environment),
            registration(
                **{
                    AUTHORIZATION_ENDPOINT: (
                        f"https://{LOOPBACK_URL_HOSTS[spelling]}:8080/oidc/authorize"
                    )
                }
            ),
        )


@pytest.mark.parametrize("scheme", ("http", "https"))
@pytest.mark.parametrize("spelling", list(LOOPBACK_URL_HOSTS))
def test_a_loopback_authorization_endpoint_is_accepted_in_development(
    spelling: str, scheme: str
) -> None:
    """The exact pair: the same addresses, one environment different.

    `http://localhost:8080/oidc/authorize` is the value E1-05 seeds, because a
    browser on the developer's host reaches the mock platform there. A loopback
    refusal written without the environment condition closes the launch door on
    every laptop and passes every refusal row above.

    Both schemes, since the development stack is cleartext and the rule above is
    written over TLS; neither may be refused here. All five spellings, so that
    widening the rule into a class cannot narrow what development accepts — a
    developer running the platform on a second loopback address is doing nothing
    wrong.
    """
    host = LOOPBACK_URL_HOSTS[spelling]
    judge(
        development_environment(),
        registration(**{AUTHORIZATION_ENDPOINT: f"{scheme}://{host}:8080/oidc/authorize"}),
    )


@pytest.mark.parametrize("spelling", list(LOOPBACK_URL_HOSTS))
@pytest.mark.parametrize("column", FETCHED_COLUMNS)
def test_a_loopback_fetched_address_is_accepted_outside_development(
    column: str, spelling: str
) -> None:
    """The composition, stated from the side where the two columns disagree.

    A platform component running beside the application — a sidecar in the same
    pod, or on the same host — is reached by this container at a loopback
    address, and both fetched columns may point there in any environment. ADR
    0077 protects exactly this shape by name in its consequences, and sweeping
    loopback out of all three columns would refuse it while protecting nothing:
    neither of these two is ever handed to a browser.

    **The mutation this kills:** the loopback class applied to every column
    rather than to the browser-facing one. **Its pair** is the refusal above,
    where the identical host under the identical environment is refused because
    the column is the one a browser reads.
    """
    host = LOOPBACK_URL_HOSTS[spelling]
    judge("production", registration(**{column: f"https://{host}:8443/lti/token"}))


def test_a_non_loopback_ip_literal_authorization_endpoint_is_accepted_outside_development() -> None:
    """The pair that keeps the class honest: an address is not the same as loopback.

    The cheapest way to satisfy a class-based rule is to widen it past the class
    — "the host is an IP literal" instead of "the host is an IP literal that is
    loopback". An institution that publishes its platform at an address rather
    than a name is then unregistrable, and every refusal row above stays green.

    TEST-NET-3 (RFC 5737), so the row is unambiguously an address, unambiguously
    not loopback, and names nobody's real host.

    **The mutation this kills:** `ipaddress.ip_address(host)` succeeding treated
    as the refusal, rather than `.is_loopback` on the parsed result. **Its pair**
    is the `127.0.0.2` row above, which the same broken rule also passes.
    """
    judge(
        "production",
        registration(
            **{AUTHORIZATION_ENDPOINT: f"https://{NON_LOOPBACK_IP_LITERAL}/lti/authorize"}
        ),
    )


def test_a_cleartext_loopback_authorization_endpoint_is_refused_outside_development() -> None:
    """Where two rules overlap, the exemption must not be the one that wins.

    `http://localhost:8080/oidc/authorize` in a deployment is the exact value an
    operator carries forward from the development stack. The transport rule
    *exempts* cleartext to this machine; the loopback rule *refuses* this column
    pointed at this machine. Written as an early return — "on this machine,
    nothing more to check" — the exemption answers first and the hole is still
    open, with every other row in this module green.

    So this is not the first loopback test with a different scheme. It is the one
    that says the rules compose rather than short-circuit, and ADR 0077 records
    the identical composition on the identical pair of rules.

    **The mutation this kills:** an on-this-machine check that returns early
    instead of continuing to the column-specific rule.
    """
    with pytest.raises(registration_error()):
        judge(
            "production",
            registration(**{AUTHORIZATION_ENDPOINT: "http://localhost:8080/oidc/authorize"}),
        )


# ---------------------------------------------------------------------------
# Rule 4 — link-local refused on the two columns this container fetches, and
# private ranges accepted everywhere. The pair is the rule: one without the other
# is either an open SSRF surface or an undeployable product.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("environment", DEPLOYMENT_ENVIRONMENTS)
@pytest.mark.parametrize("spelling", list(LINK_LOCAL_URL_HOSTS))
@pytest.mark.parametrize("column", FETCHED_COLUMNS)
def test_a_link_local_fetched_address_is_refused_outside_development(
    column: str, spelling: str, environment: str
) -> None:
    """The two columns fetched on every launch may not name the link-local range.

    `jwks_url` and `auth_token_url` are the only addresses in this system that a
    stored row causes this container to fetch, which makes a registration an SSRF
    surface as well as a trust anchor. `169.254.169.254` is where the cloud
    metadata service lives on every major provider — the one address inside a
    container that answers credentials to any request that reaches it — and no
    legitimate LMS is there.

    Both families, because a rule written over `169.254.0.0/16` alone leaves
    `fe80::/10`, and a container with IPv6 reaches the same class of thing
    through it.

    **The mutation this kills:** no link-local rule, and a link-local rule
    written over the IPv4 range only. **The near miss that must stay green:** the
    private ranges below, which are the ordinary deployment this must not refuse.

    **https**, so neither the transport rule nor anything else can be what
    refuses these rows.
    """
    with pytest.raises(registration_error()):
        judge(
            environment_named(environment),
            registration(
                **{column: f"https://{LINK_LOCAL_URL_HOSTS[spelling]}/.well-known/jwks.json"}
            ),
        )


@pytest.mark.parametrize("spelling", list(LINK_LOCAL_URL_HOSTS))
@pytest.mark.parametrize("column", FETCHED_COLUMNS)
def test_a_link_local_fetched_address_is_accepted_in_development(
    column: str, spelling: str
) -> None:
    """The environment pair for rule 4, and it is not ceremony.

    Every other rule here is switched off in development so that the mock's own
    addresses seed, and a rule that kept firing there would be the one difference
    a developer meets as an unexplained refusal from `make seed` after moving a
    service. The ticket's decision is that development accepts everything.

    **The mutation this kills:** the link-local rule written without the
    environment condition, which passes every refusal row above.
    """
    judge(
        development_environment(),
        registration(**{column: f"https://{LINK_LOCAL_URL_HOSTS[spelling]}/.well-known/jwks.json"}),
    )


@pytest.mark.parametrize("spelling", list(PRIVATE_URL_HOSTS))
@pytest.mark.parametrize("column", EVERY_COLUMN)
def test_a_private_range_address_is_accepted_on_every_column_outside_development(
    column: str, spelling: str
) -> None:
    """An institution's LMS on a private address is an ordinary deployment.

    This is the near-miss half of rule 4 and the reason the ticket asks for the
    position to be taken explicitly rather than inherited. The cheapest way to
    close an SSRF surface is to refuse every address that is not publicly
    routable, and that rule would refuse a university running Canvas on
    `10.0.0.5` behind its own network — which is a very ordinary way for an
    institution to run an LMS, and which no test above would notice.

    All three columns, including the browser-facing one: a browser on the
    institution's network resolves a private address perfectly well.

    **The mutation this kills:** `not ip.is_global` used as the refusal, which
    covers loopback, link-local and private in one line and reads like a
    tightening.
    """
    host = PRIVATE_URL_HOSTS[spelling]
    judge("production", registration(**{column: f"https://{host}/lti/token"}))


# ---------------------------------------------------------------------------
# Absence. Both new columns are nullable, and NULL means "not stated".
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("environment", ("production", "staging"))
@pytest.mark.parametrize("column", NULLABLE_COLUMNS)
def test_a_null_address_passes_the_chokepoint_outside_development(
    column: str, environment: str
) -> None:
    """NULL is not an address, so there is nothing here for these rules to judge.

    Both new columns are nullable by decision: an existing registration predates
    them, and NULL means "not stated" rather than a default. A validator that
    refused NULL would make the migration need a fabricated backfill, and it
    would refuse every registration an administrator has not finished — which is
    a different situation from one written wrongly, with a different repair. The
    seed itself no longer writes a NULL into either column: E1-05 filled the
    authorization endpoint and E1-06 filled `auth_token_url` when the endpoint it
    names came to exist, so what this rule protects now is the *unfinished*
    registration rather than this repository's own.

    **The mutation this kills:** a rule that treats a missing value as a failed
    scheme check — `url.startswith("https://")` on `None` raises, and a rule
    written as `not value.startswith(...)` refuses it. **What this does not
    say:** that a NULL `authorization_endpoint` is usable. It is refused at the
    launch, not at the write, and
    `tests/integration/test_registration_endpoints_are_per_platform.py` is where
    that is asserted.
    """
    judge(environment, registration(**{column: None}))


@pytest.mark.parametrize("column", NULLABLE_COLUMNS)
def test_a_null_address_passes_the_chokepoint_in_development(column: str) -> None:
    """The same in development, where a half-finished registration is likeliest.

    Its own row rather than a parameter of the test above, because a rule that
    refused NULL only in development would be invisible to every deployment row
    here — and development is where a registration gets typed in a piece at a
    time. It stopped being a statement about `scripts/seed.py` when E1-06 filled
    the second of the two columns; the seed now writes an address into both.
    """
    judge(development_environment(), registration(**{column: None}))


# ---------------------------------------------------------------------------
# What the refusal says. The house rule is ADR 0056's and ADR 0077's: name the
# field, quote no value.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("column", EVERY_COLUMN)
def test_the_refusal_names_the_column_and_does_not_quote_the_value(column: str) -> None:
    """What the operator reads: which column is wrong, and not the value they wrote.

    Both halves, because each is satisfiable without the other. A refusal that
    says only "an invalid registration address" leaves whoever is registering a
    platform to work out which of three columns carries it. A refusal that quotes
    the configured value back writes a deployment's registration into a log
    stream and into whatever gets pasted when somebody asks for help (SPEC §10),
    and this chokepoint is called by a seed that prints its own errors and later
    by a console that renders them to a person.

    Nothing else about the wording is pinned, and the host may appear — it is
    what is being refused. What is asserted is that the whole value does not, and
    the distinctive query above is what makes that a statement about this string
    rather than about a substring that could turn up by accident.

    **The mutation this kills:** an f-string refusal built from the offending
    address, and a message that names the rule without naming the column.
    """
    with pytest.raises(registration_error()) as refusal:
        judge("production", registration(**{column: OFFENDING_MOCK_URL}))

    message = str(refusal.value)
    assert column.lower() in message.lower(), (
        f"The refusal does not name `{column}`: {message!r}. Three columns can carry a refused "
        "address and whoever reads this has to learn which one did."
    )
    assert OFFENDING_MOCK_URL not in message and OFFENDING_DETAIL not in message, (
        f"The refusal quotes the address back: {message!r}. The host is what is being refused and "
        "may be named; the rest is the deployment's own configuration, and a refusal reaches a "
        "container log (SPEC §10)."
    )


# ---------------------------------------------------------------------------
# Controls. Two constants decide most of this module, and a stale one refuses
# nothing while reporting exactly what a correct one reports (`docs/MISTAKES.md`
# entry 35). **A red in this section means these tests are broken, not the code.**
# Nothing here imports the application except the last row, which reads one
# already-shipped constant.
# ---------------------------------------------------------------------------


def test_the_refused_host_is_the_compose_service_the_mock_platform_runs_as(
    mock_lms_service: str,
) -> None:
    """A control: the host this module refuses is the name SPEC §7.2 gives the service.

    A written-out catalog goes stale without anything failing, because a rule
    refusing a name nothing runs under reports every registration clean.
    `mock_lms_service` is `tests/fixtures/lti_services.py`'s single answer to
    "what is the mock platform called", used by every other module that reasons
    about it.
    """
    assert mock_lms_service == MOCK_SERVICE, (
        f"This module refuses the host {MOCK_SERVICE!r} and the mock platform runs as the Compose "
        f"service {mock_lms_service!r}. Every mock refusal above would then be about a name "
        "nothing on this stack answers to."
    )


def test_the_seeded_key_set_address_is_the_one_the_mock_registration_carries(
    base_compose: dict[str, Any], mock_lms_config: Any
) -> None:
    """A control: the development registration above is the one the platform publishes.

    `DEVELOPMENT_REGISTRATION` is what
    `test_the_registration_the_seed_writes_is_accepted_in_development` asserts is
    accepted, and if its key set URL drifted from the platform's own the
    acceptance would be about an address nothing writes — green, and saying
    nothing about whether the seed can still run.

    Two authorities, because the key-set URL is not a Compose literal: the
    platform composes it from its own issuer and `mock-lms/app/config.py`'s
    `JWKS_PATH`, which is the currency a guard reading only the Compose
    environment block cannot see (`docs/MISTAKES.md` entry 35, found on E0-31).
    """
    services = base_compose.get("services") or {}
    service = services.get(MOCK_SERVICE) or {}
    environment = service.get("environment") if isinstance(service, dict) else None
    assert isinstance(environment, dict) and environment, (
        f"`docker-compose.yml` gives the `{MOCK_SERVICE}` service no mapping-shaped "
        "`environment:` block, so this control has nothing to compare against and would report "
        "the constant fresh whatever it says. ADR 0037 puts those values there as literals."
    )
    issuer = environment.get("MOCK_LMS_ISSUER")
    jwks_path = getattr(mock_lms_config, "JWKS_PATH", None)
    assert issuer and isinstance(jwks_path, str) and jwks_path.startswith("/"), (
        f"The mock platform is configured with issuer {issuer!r} and `JWKS_PATH` {jwks_path!r}, so "
        "the key set address cannot be composed and this control would pass over an absence."
    )
    assert DEVELOPMENT_REGISTRATION[JWKS_URL] == f"{issuer}{jwks_path}", (
        f"This module's development registration names {DEVELOPMENT_REGISTRATION[JWKS_URL]!r} and "
        f"the mock platform publishes its key set at {issuer}{jwks_path}. The acceptance test "
        "built on it would then be about an address the seed never writes."
    )


def test_the_background_registration_names_no_mock_and_no_special_address() -> None:
    """A control: the values every refusal and every acceptance is measured against.

    `registration()` is the background of the whole module: a refusal row sets
    two columns from it and one bad value, and an acceptance row sets all three.
    If any of the three carried the mock's name, a loopback host or a link-local
    address, every refusal above would pass whatever value it set — the rule
    firing on the background rather than on the subject — and every acceptance
    would be asserting the opposite of the ticket.

    Arithmetic on this module's own constants, which is why it can be relied on
    to say something about the rest.
    """
    for column, value in DEPLOYED_REGISTRATION.items():
        assert value.startswith("https://"), (
            f"The background value for `{column}` is {value!r}, which is not https — so every "
            "refusal built on it could be the transport rule firing on a neighbour."
        )
        for host in (MOCK_SERVICE, *LOOPBACK_URL_HOSTS.values(), *LINK_LOCAL_URL_HOSTS.values()):
            assert host.strip("[]") not in value, (
                f"The background value for `{column}` is {value!r}, which contains {host!r}. Every "
                "test built on `registration()` then has a refusable address in its background."
            )


def test_the_development_environment_name_is_read_from_its_one_definition() -> None:
    """A control: `app.config.DEVELOPMENT_ENVIRONMENT` exists and is a name.

    Every acceptance row in this module is parametrised on it, and every
    `NON_DEVELOPMENT_ENVIRONMENTS` row is built by formatting it in. If it were
    absent or empty, `environment_named` would produce rows that are not
    deployments and the refusals would be asserting the development case.
    """
    assert development_environment().strip() == development_environment(), (
        "`DEVELOPMENT_ENVIRONMENT` carries surrounding whitespace, so the rows built from it are "
        "not the names a deployment would set."
    )
