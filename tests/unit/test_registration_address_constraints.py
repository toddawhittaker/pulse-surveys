"""What a legitimate registration address looks like — ticket E1-05, criterion 3.

E0-24 item 1 left `jwks_url` credential-equivalent and unconstrained: it decides
which keys may sign an accepted launch, it is fetched server-side on every
launch, and until this ticket any string at all could be written into it. E1-05
adds two more columns beside it — the platform's browser-facing
`authorization_endpoint` and its tool-facing `auth_token_url` — and fixes the
floor for all three at one chokepoint.

**The subject is two functions.** `app.models.lti.refuse_invalid_registration_addresses`
is called by every writer of an `lti_platform` row; it takes the environment name
and the three addresses and either returns or raises
`app.models.lti.RegistrationAddressError`.
`app.models.lti.refuse_invalid_fetched_address` is the same rules applied to one
address at a time, by the code that is about to *fetch* it — ADR 0096 added it for
the roster walk, and the cleanup batch that adds rule 5 gives it the two
parameters the walk needs. Nothing here reaches the database: the rules read
`ENVIRONMENT`, which the database does not hold, which is why the chokepoint is a
validator and not a `CHECK` constraint.

**Rule 5, and what it reversed.** ADR 0081 measured its own residue and named the
price: rules 3 and 4 judge *spellings*, so `127.1`, `2130706433`, `0x7f.0.0.1` and
any name a resolver answers with a refused address all walk past them. The
cleanup batch closes that by resolving the host and judging every address that
comes back — an address that is not `is_global` is refused, except a loopback
address on a column outside `LOOPBACK_REFUSED_COLUMNS`, which stays admitted
because an operator registering a cleartext key-set sidecar beside the
application is doing it on purpose (ADR 0077, ADR 0096).

That **reverses ADR 0081's acceptance of private ranges**, and the reversal is
stated here rather than left to be discovered: `10.0.0.5` on a registration
column was accepted by that record's decision and is refused by rule 5, because a
resolved private address is exactly the SSRF the batch exists to close and there
is no way to tell "an institution's own LMS" from "an internal service holding a
valid certificate" at the point of judgment. The tests below that used to assert
the acceptance now assert the refusal, and they still carry the development pair,
because in development every rule here is still off.

**No test in this module performs real DNS.** Every call goes through `judge` or
`judge_fetched`, which inject a resolver this file describes. A test that reached
a name server would be green on a developer's machine and red in CI, or the
reverse, and would be measuring the machine rather than the rules
(`docs/MISTAKES.md` entry 40's shape, arriving through a resolver instead of an
environment variable).

**Six rules, and every one of them is asserted from both sides.** A validator
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
     lives at `169.254.169.254` and no legitimate LMS does. Private ranges were
     accepted everywhere under this rule and **rule 5 refuses them**; the near
     miss that now keeps the class honest is a globally-routable address, not a
     private one.
  5. **The host is resolved and every returned address is judged**, outside
     development: an address that is not `is_global` is refused, except loopback
     on a column outside `LOOPBACK_REFUSED_COLUMNS`, and an unresolvable host is
     refused outright.
  6. **An address whose authority two parsers disagree about is refused**, on the
     fetched column and on the two registration columns this container fetches.
     The E1 boundary fix round added it after a security pass measured the
     disagreement against the installed libraries; the re-pass then measured the
     first form of it being defeated, because the rule compared the judged host
     with *itself* put through the client's parser rather than with the host the
     client will actually dial. The comparison is between the two readings, and
     the acceptance rows — an IDN, a punycoded label, a trailing dot, a port,
     userinfo, IP literals — are what stop it being bought by refusing everything
     unusual. Its own two sections near the foot of this module say why each
     vector is built the way it is.

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

**E3-02 adds one test to the foot of this module and nothing else**, and it is the
one exception to the paragraph above: `test_both_gradebook_columns_are_judged_and_
refuse_loopback` is red on today's tree, on the two columns that ticket adds to the
two tuples this file already pins. It is here rather than in a module of its own
because a second home for "what is in `FETCHED_COLUMNS`" would be a second record
of one fact, and one of the two would go stale.

ADR 0077's own refusal tests, in `tests/unit/test_oidc_provider_configuration.py`,
are untouched by this ticket and must keep passing. This module borrows that
one's vocabulary where the question is the same and says where it differs; the
ticket requires the decision itself to be E1-05's own, in its own ADR.
"""

import inspect
from collections.abc import Callable, Mapping, Sequence
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

# Private ranges. These were **accepted** under ADR 0081's four rules and are
# **refused** under rule 5, and the reversal is the batch's own decision rather
# than a drift: a resolved private address is the SSRF E1-11's residual finding is
# about — an internal service holding a valid certificate on an RFC 1918 or
# split-horizon address, fetched with the tool's Bearer token attached — and
# nothing at the point of judgment can tell it from an institution's own LMS. The
# price ADR 0081 named for the other direction is real and is now paid: a
# university running Canvas on `10.0.0.5` cannot be registered in a deployment.
PRIVATE_URL_HOSTS = {
    "RFC 1918": "10.0.0.5",
    "the other RFC 1918 block": "192.168.10.4",
    "an IPv6 unique local address": "[fd00::5]",
}

# An address that is emphatically neither loopback nor private nor link-local, so
# that "an IP literal" cannot stand in for any of the three classes.
#
# **It was `203.0.113.10` until rule 5, and that stopped working.** TEST-NET-3
# (RFC 5737) is reserved for documentation, which makes `ipaddress` report
# `is_global` false for it — so under a rule that refuses every resolved address
# which is not globally routable, the documentation range is refused and a test
# using it as "an ordinary public address" asserts the opposite of what it says.
# The same trap holds `192.0.2.0/24`. `93.184.216.34` is globally routable, which
# is the only property this row needs.
NON_LOOPBACK_IP_LITERAL = "93.184.216.34"

# ---------------------------------------------------------------------------
# Rule 5: the host is resolved and every returned address is judged.
# ---------------------------------------------------------------------------

# Two globally routable addresses and one that is not. Held against `ipaddress`
# itself by a control at the foot of this module, because the whole of rule 5 is
# `is_global` and a vector on the wrong side of it turns a refusal test into an
# acceptance test with no visible change (`docs/MISTAKES.md` entry 3).
A_GLOBAL_ADDRESS = "93.184.216.34"
ANOTHER_GLOBAL_ADDRESS = "8.8.8.8"
A_PRIVATE_ADDRESS = "10.0.0.7"
A_LOOPBACK_ADDRESS = "127.0.0.1"

# ADR 0081's measured residue, verbatim: the spellings that reach a refused
# address while parsing as no address at all. `ipaddress.ip_address` refuses every
# one of them, which is why rules 3 and 4 walk past them and why closing this
# needs a resolver rather than another spelling in a list.
RESIDUE_LOOPBACK_HOSTS = {
    "a shortened dotted quad": "127.1",
    "a bare decimal": "2130706433",
    "dotted hex": "0x7f.0.0.1",
    "a name a resolver answers with loopback": "sidecar.platform.invalid",
}

# A name that resolves to a private address — the case ADR 0081 records as
# `metadata.google.internal` and the one E1-11's residual finding is about: an
# internal service holding a valid certificate on an address inside the network
# the worker sits in. Spelled `.invalid` (RFC 2606) so that a stub is the only
# thing that could ever answer it.
AN_INTERNAL_NAME = "internal.platform.invalid"

# A name nothing answers for. The design refuses an unresolvable host outright —
# unresolvable is unjudgeable — in both of the two shapes a resolver fails in.
AN_UNRESOLVABLE_NAME = "nowhere.platform.invalid"
AN_EMPTY_ANSWER_NAME = "silent.platform.invalid"

# The two columns of `refuse_invalid_fetched_address` this module drives, and the
# split ADR 0096 draws between them: the roster address is chosen by the platform
# at run time and refuses loopback, the key set address is written by an operator
# and admits it. Held against `app.models.lti`'s own two tuples by a control.
ROSTER_ADDRESS_COLUMN = "lms_context_memberships_url"

# The two gradebook columns E3-02 adds to `section`, spelled by that ticket's work
# order. **Not this module's choice** in any part: `lms_ags_line_items_url` is the
# AGS line-item container a launch advertises, `lms_`-marked because the platform
# supplies it; `ags_line_item_url` is the id of the line item this tool creates in
# that container, which is Pulse's own and therefore carries no `lms_` prefix.
# Both are addresses this container fetches — E3-04 lists and creates in the
# container, E3-05 and E3-06 post to the line item — which is what puts them in
# both tuples below.
AGS_LINE_ITEMS_COLUMN = "lms_ags_line_items_url"
AGS_LINE_ITEM_COLUMN = "ags_line_item_url"

# The host a development stack's own roster lives on, for the exemption. Compared
# by equality against the parsed hostname, never as a substring — the near miss is
# the fourth row of `NON_MOCK_URL_SPELLINGS` one level out.
AN_EXEMPT_HOST = "mock-lms"
A_HOST_THE_EXEMPT_ONE_PREFIXES = "mock-lms.evil.example"

# Every hostname this module drives, and what a resolver answers for it. IP
# literals are not listed: the stub answers a literal with itself, which is what
# `socket.getaddrinfo` does, and which leaves open whether the implementation
# short-circuits a literal or resolves it like anything else.
DEFAULT_RESOLUTIONS: dict[str, tuple[str, ...]] = {
    DEPLOYED_HOST: (A_GLOBAL_ADDRESS,),
    "localhost": (A_LOOPBACK_ADDRESS,),
    MOCK_SERVICE: (A_GLOBAL_ADDRESS,),
    f"{MOCK_SERVICE}.example.edu": (A_GLOBAL_ADDRESS,),
    f"{MOCK_SERVICE}-2.example.edu": (A_GLOBAL_ADDRESS,),
    f"staging-{MOCK_SERVICE}": (A_GLOBAL_ADDRESS,),
}

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


def refuse_fetched_address() -> Any:
    """The per-address chokepoint, imported inside the test so a missing one fails loudly.

    ADR 0096's helper: the same rules applied to one address that is about to be
    *fetched*, by the roster walk and by the launch-time writer. Imported the way
    `refuse_addresses` above is, and for the same reason.
    """
    try:
        from app.models.lti import refuse_invalid_fetched_address
    except ImportError as absent:
        pytest.fail(
            "`app.models.lti` exposes no `refuse_invalid_fetched_address` "
            f"({absent}). ADR 0096 puts the per-address half of the registration rules there, "
            "called once per URL the roster walk is about to fetch and once by the launch-time "
            "writer storing an address out of a claim."
        )
    return refuse_invalid_fetched_address


def resolution_key(host: str) -> str:
    """A hostname as a resolver keys it: unbracketed, one trailing dot off, folded."""
    return host.strip().strip("[]").rstrip(".").lower()


def default_resolution(host: str) -> Sequence[str]:
    """What a resolver answers for the hostnames this module already drove.

    Every test written before rule 5 goes through this, so that the calls those
    tests always made keep meaning what they meant — and so that not one of them
    reaches a name server. An IP literal answers itself, which is what
    `socket.getaddrinfo` does with one and which deliberately leaves open whether
    the implementation short-circuits a literal or resolves it like anything else.

    A hostname nobody described stops the test rather than being reported as
    unresolvable: "unresolvable" is a *refusal* under rule 5, so a stub that
    guessed would turn a test driving an undescribed host into a green refusal
    (`docs/MISTAKES.md` entry 3).
    """
    from ipaddress import ip_address

    key = resolution_key(host)
    if key in DEFAULT_RESOLUTIONS:
        return DEFAULT_RESOLUTIONS[key]
    try:
        ip_address(key)
    except ValueError:
        raise AssertionError(
            f"The chokepoint asked a resolver about {host!r}, which this module never described "
            f"(it describes {sorted(DEFAULT_RESOLUTIONS)}). Add the host to `DEFAULT_RESOLUTIONS` "
            "with the answer the test means, or hand the test its own resolver — nothing here may "
            "reach real DNS."
        ) from None
    return (key,)


def resolves(function: Any) -> bool:
    """Whether this build's chokepoint takes the resolution seam rule 5 needs."""
    return "resolve" in inspect.signature(function).parameters


def require_resolution_seam(function: Any, *extra: str) -> None:
    """Stop with a named failure where the parameters rule 5 needs are absent.

    The module's own idiom, one level in: an absent *parameter* is reported as a
    failed assertion naming what the cleanup batch is asked to add, rather than as
    a `TypeError` about an unexpected keyword — which reads as a broken test.
    """
    parameters = inspect.signature(function).parameters
    missing = [name for name in ("resolve", *extra) if name not in parameters]
    if missing:
        pytest.fail(
            f"`{getattr(function, '__name__', function)}` takes no {missing} parameter — it takes "
            f"{sorted(parameters)}. Rule 5 resolves the URL's host and judges every address that "
            "comes back, and `resolve` is the seam that keeps that out of real DNS: "
            "`refuse_invalid_registration_addresses(environment, *, authorization_endpoint, "
            "jwks_url, auth_token_url, resolve=None)` and "
            "`refuse_invalid_fetched_address(environment, *, column, address, resolve=None, "
            "development_exempt_host=None)`. Until the parameter is there, this test would "
            "either measure a name server or measure nothing."
        )


def judge(
    environment: str,
    addresses: Mapping[str, str | None],
    *,
    resolve: Callable[[str], Sequence[str]] | None = None,
) -> None:
    """Put one registration through the chokepoint under one environment name.

    `resolve` is passed where this build's chokepoint takes it and omitted where
    it does not, so the tests written before rule 5 keep asserting exactly what
    they asserted — and, once it does take it, resolve through this module's own
    table rather than through DNS. A test whose *subject* is rule 5 calls
    `judge_with_resolver` instead, which requires the parameter and says so.
    """
    function = refuse_addresses()
    if not resolves(function):
        function(environment, **dict(addresses))
        return
    resolver = default_resolution if resolve is None else resolve
    function(environment, **dict(addresses), resolve=resolver)


def judge_with_resolver(
    environment: str,
    addresses: Mapping[str, str | None],
    resolve: Callable[[str], Sequence[str]],
) -> None:
    """The same, for a test whose subject is rule 5: the seam is required, not optional."""
    function = refuse_addresses()
    require_resolution_seam(function)
    function(environment, **dict(addresses), resolve=resolve)


def judge_fetched(
    environment: str,
    *,
    column: str,
    address: str | None,
    resolve: Callable[[str], Sequence[str]],
    development_exempt_host: str | None = None,
) -> Any:
    """Put one fetched address through ADR 0096's helper, and answer what it returned.

    The return value is part of the contract rather than incidental: rule 5 hands
    back the tuple of addresses it resolved, which is what the roster sync pins its
    connection to, and `None` where it did not resolve at all.
    """
    function = refuse_fetched_address()
    require_resolution_seam(function, "development_exempt_host")
    return function(
        environment,
        column=column,
        address=address,
        resolve=resolve,
        development_exempt_host=development_exempt_host,
    )


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

    A globally-routable address, so the row is unambiguously an address and
    unambiguously not loopback. It was TEST-NET-3 (RFC 5737) until rule 5, which
    judges `is_global` and reports false for every documentation range — see
    `test_the_address_vectors_sit_on_the_side_of_is_global_this_module_claims`,
    which holds both halves of that trap.

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
# Rule 4 — link-local refused on the two columns this container fetches. Private
# ranges were the acceptance that kept this rule honest and rule 5 reverses them;
# the pair that keeps *rule 5* honest is the globally-routable address, which is
# in the rule 5 section below.
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
def test_a_private_range_address_is_refused_on_every_column_outside_development(
    column: str, spelling: str
) -> None:
    """Rule 5 refuses a resolved address that is not globally routable, on every column.

    **This assertion is the reverse of the one that stood here**, and the reversal
    is the batch's, stated rather than slipped in. ADR 0081 accepted private
    ranges everywhere and rejected `not ip.is_global` by name, on the argument
    that a university running Canvas on `10.0.0.5` behind its own network is an
    ordinary deployment. E1-11's residual finding is the other side of that
    argument: an internal service holding a valid public certificate on an RFC
    1918 or split-horizon address passes every one of the four rules, and this
    tool then issues a GET to it with its NRPS Bearer token attached. Nothing at
    the point of judgment distinguishes the two, so rule 5 refuses both.

    All three columns, and both families: RFC 1918, the second RFC 1918 block, and
    an IPv6 unique local address, which is `is_global` false for the same reason
    and which a rule written over the IPv4 blocks alone would let through.

    **The mutation this kills:** rule 5 written as a loopback-and-link-local class
    rather than as `is_global`, which passes every other refusal in this module.
    **Its pairs, both of which must stay green:** the development row below, where
    every rule here is off, and the globally-routable address rows in the rule 5
    section, which are what stop "refuse every IP literal" from passing this.
    """
    host = PRIVATE_URL_HOSTS[spelling]
    with pytest.raises(registration_error()):
        judge("production", registration(**{column: f"https://{host}/lti/token"}))


@pytest.mark.parametrize("spelling", list(PRIVATE_URL_HOSTS))
@pytest.mark.parametrize("column", EVERY_COLUMN)
def test_a_private_range_address_is_accepted_on_every_column_in_development(
    column: str, spelling: str
) -> None:
    """The environment pair for the reversal above, and the seed depends on it.

    Rule 5 joins the other four in being switched off under the development name.
    A developer running a platform, a key-set sidecar or a roster service on a
    private address inside Compose is doing nothing wrong, and the demo stack's
    own addresses are on a container network — a rule that fired here would meet
    them as an unexplained refusal from `make seed`.

    **The mutation this kills:** rule 5 written without the environment condition,
    which passes every refusal row above.
    """
    host = PRIVATE_URL_HOSTS[spelling]
    judge(development_environment(), registration(**{column: f"https://{host}/lti/token"}))


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
# Rule 5, at the registration-write surface. The host is resolved and every
# address that comes back is judged. Applied **after** rules 1-4, so an address a
# spelling rule refuses is never resolved (`docs/MISTAKES.md` entry 29: a value
# repaired — or here, looked up — before the check that should have refused it).
# ---------------------------------------------------------------------------


def described(resolving: Any, answers: Mapping[str, Any]) -> Any:
    """A stub resolver answering this module's background hosts, plus `answers`.

    The background matters: every row here sets one column and takes the other two
    from `registration()`, whose host has to resolve to something acceptable or
    the refusal under test could be rule 5 firing on a neighbour
    (`docs/MISTAKES.md` entry 3, which this module already guards for the other
    four rules).
    """
    return resolving({**DEFAULT_RESOLUTIONS, **answers})


def test_both_chokepoints_take_the_resolution_seam_rule_five_needs() -> None:
    """The parameters this batch adds, named once so the rest of the section has a cause.

    Every rule 5 test below fails on this same absence, and reading forty of those
    is how a missing parameter gets mistaken for forty broken tests. This is the
    one that says it plainly: the two functions grow a `resolve` argument, and the
    fetched one grows `development_exempt_host` beside it, exactly as the batch's
    settled design spells them.

    It is also what stops a quieter failure. `judge` passes `resolve` only where
    this build's chokepoint takes it, so that the tests written before rule 5 keep
    asserting what they asserted — and if the parameter were ever renamed, those
    tests would silently fall back to the default resolver and start reaching real
    DNS. This assertion is what makes that a red rather than a suite that goes
    green or red depending on the machine's name server.
    """
    require_resolution_seam(refuse_addresses())
    require_resolution_seam(refuse_fetched_address(), "development_exempt_host")


@pytest.mark.parametrize("spelling", list(RESIDUE_LOOPBACK_HOSTS))
def test_a_spelling_that_resolves_to_loopback_is_refused_on_the_browser_facing_column(
    resolving: Any, spelling: str
) -> None:
    """ADR 0081's measured residue, closed: the address decides, not the spelling.

    Four vectors, and they are that record's own list rather than this module's
    invention: `127.1`, `2130706433`, `0x7f.0.0.1` and a name a resolver answers
    with a loopback address. Every one of them reaches `127.0.0.1` and every one
    of them parses as no address at all, so rule 3 — which asks
    `ipaddress.ip_address(host).is_loopback` — walks straight past them. That is
    the whole reason closing this needs a resolver rather than a fifth spelling in
    a list, and it is why the residue survived a class-based rule that was already
    written as a class.

    What a deployment that registered one of these answers every launch with is a
    redirect to a port on the launching person's own computer — rule 3's own
    finding, arriving through a spelling that rule cannot read.

    **The mutation this kills:** rule 5 written only for hosts that already parse
    as an address, which is a no-op over exactly these four vectors and passes
    every other test in this module. **Its pair** is the next test, where the same
    four spellings are admitted on the two columns that admit loopback.
    """
    host = RESIDUE_LOOPBACK_HOSTS[spelling]
    with pytest.raises(registration_error()):
        judge_with_resolver(
            "production",
            registration(**{AUTHORIZATION_ENDPOINT: f"https://{host}:8080/oidc/authorize"}),
            described(resolving, {host: (A_LOOPBACK_ADDRESS,)}),
        )


@pytest.mark.parametrize(
    "host",
    [*RESIDUE_LOOPBACK_HOSTS.values(), A_LOOPBACK_ADDRESS],
)
@pytest.mark.parametrize("column", FETCHED_COLUMNS)
def test_a_spelling_that_resolves_to_loopback_is_admitted_on_a_column_that_admits_loopback(
    resolving: Any, column: str, host: str
) -> None:
    """The split ADR 0096 drew survives rule 5: the sidecar is still registrable.

    An operator registering a key-set or token sidecar reached at a loopback
    address, in the same pod, is doing it on purpose — ADR 0077 protects the shape
    by name and ADR 0096 kept it when it added loopback to the roster column. Rule
    5 adds a *resolution* dimension to that split; it does not reopen it. So
    `127.1` on `jwks_url` is a badly-spelled sidecar and stays admitted, while the
    same string on `authorization_endpoint` is refused by the test above.

    The literal `127.0.0.1` row is here as the control inside the pair: it is the
    spelling that was always admitted, so a red on it alone means the split broke
    rather than that the residue did.

    **The mutation this kills:** rule 5 written as "no resolved address may be
    non-global", with no exception for loopback on the columns outside
    `LOOPBACK_REFUSED_COLUMNS` — which passes every refusal above and makes a
    supported deployment unregistrable.
    """
    judge_with_resolver(
        "production",
        registration(**{column: f"https://{host}:8443/lti/token"}),
        described(resolving, {host: (A_LOOPBACK_ADDRESS,)}),
    )


@pytest.mark.parametrize("column", EVERY_COLUMN)
def test_a_name_that_resolves_to_a_private_address_is_refused_outside_development(
    resolving: Any, column: str
) -> None:
    """E1-11's residual finding at the write surface: the name is innocent, the address is not.

    `metadata.google.internal` is ADR 0081's own example and the shape is general:
    a host that parses as no address, carries a valid certificate, passes rules
    1-4 without a mark, and resolves to something inside the network this
    container sits in. Two of these three columns are fetched by this tool on
    every launch, so a registration naming one is an outbound authenticated
    request to an internal service.

    **The mutation this kills:** rule 5 applied only to hosts that are already IP
    literals — which closes the `10.0.0.5` case and leaves the case that actually
    needs a resolver open. **Its pair** is the next test, where the identical name
    resolving to a globally-routable address is accepted.
    """
    with pytest.raises(registration_error()):
        judge_with_resolver(
            "production",
            registration(**{column: f"https://{AN_INTERNAL_NAME}/lti/token"}),
            described(resolving, {AN_INTERNAL_NAME: (A_PRIVATE_ADDRESS,)}),
        )


@pytest.mark.parametrize("column", EVERY_COLUMN)
def test_a_name_that_resolves_to_a_global_address_is_accepted_outside_development(
    resolving: Any, column: str
) -> None:
    """The pair without which every rule 5 refusal is satisfied by refusing everything.

    A real LMS is a hostname that resolves to a public address, and that is the
    only registration anybody actually writes. A rule 5 that refused whenever it
    resolved anything at all passes every refusal in this section and makes Pulse
    registrable nowhere — the same cheapest-wrong-implementation this module's
    original acceptance rows were written against, one rule later.
    """
    judge_with_resolver(
        "production",
        registration(**{column: f"https://{AN_INTERNAL_NAME}/lti/token"}),
        described(resolving, {AN_INTERNAL_NAME: (A_GLOBAL_ADDRESS,)}),
    )


@pytest.mark.parametrize("column", EVERY_COLUMN)
def test_a_host_resolving_to_a_global_and_a_private_address_is_refused_outside_development(
    resolving: Any, column: str
) -> None:
    """Every returned address is judged, not the first one.

    A name with two A records — one public, one on the internal network — is an
    ordinary split-horizon arrangement, and it is also the way past a rule that
    reads `resolve(host)[0]` and stops. Which record a resolver returns first is
    not stable: it depends on the resolver, the cache and, for a hostile platform,
    on what the platform's own DNS chooses to answer at the moment of the check.

    **The mutation this kills:** `addresses[0]` judged instead of every address —
    which passes the single-address refusal above and every acceptance here.
    **Its pair** is the next test, where two addresses that are both global are
    accepted, so this cannot be satisfied by refusing any multi-address answer.
    """
    with pytest.raises(registration_error()):
        judge_with_resolver(
            "production",
            registration(**{column: f"https://{AN_INTERNAL_NAME}/lti/token"}),
            described(resolving, {AN_INTERNAL_NAME: (A_GLOBAL_ADDRESS, A_PRIVATE_ADDRESS)}),
        )


@pytest.mark.parametrize("column", EVERY_COLUMN)
def test_a_host_resolving_to_two_global_addresses_is_accepted_outside_development(
    resolving: Any, column: str
) -> None:
    """The pair for "every address is judged": more than one answer is not itself a fault.

    A load-balanced LMS answers several A records and all of them are ordinary.
    Without this row, the mixed-answer refusal above is satisfied by a rule that
    refuses any host resolving to more than one address.
    """
    judge_with_resolver(
        "production",
        registration(**{column: f"https://{AN_INTERNAL_NAME}/lti/token"}),
        described(resolving, {AN_INTERNAL_NAME: (A_GLOBAL_ADDRESS, ANOTHER_GLOBAL_ADDRESS)}),
    )


@pytest.mark.parametrize("column", EVERY_COLUMN)
def test_a_host_resolving_to_an_ipv4_mapped_private_address_is_refused_outside_development(
    resolving: Any, column: str
) -> None:
    """The mapped form is unwrapped before it is judged, as rule 3 already unwraps it.

    `::ffff:10.0.0.7` is `10.0.0.7` reached over an IPv6 socket, and it is the
    form a dual-stack resolver hands back. A rule that asked `is_global` of the
    wrapper without unwrapping it reads a different answer from the one the packet
    will get, and the existing loopback rule already faced this exact quirk — so
    not unwrapping here is `docs/MISTAKES.md` entry 13, the same hazard in the
    second of the two places that face it.

    **Its pair** is the next test: the mapped form of a global address is
    accepted, so this cannot be satisfied by refusing every mapped address.
    """
    with pytest.raises(registration_error()):
        judge_with_resolver(
            "production",
            registration(**{column: f"https://{AN_INTERNAL_NAME}/lti/token"}),
            described(resolving, {AN_INTERNAL_NAME: (f"::ffff:{A_PRIVATE_ADDRESS}",)}),
        )


@pytest.mark.parametrize("column", EVERY_COLUMN)
def test_a_host_resolving_to_an_ipv4_mapped_global_address_is_accepted_outside_development(
    resolving: Any, column: str
) -> None:
    """The pair: unwrapping must decide the class, not the wrapper's presence."""
    judge_with_resolver(
        "production",
        registration(**{column: f"https://{AN_INTERNAL_NAME}/lti/token"}),
        described(resolving, {AN_INTERNAL_NAME: (f"::ffff:{A_GLOBAL_ADDRESS}",)}),
    )


# ---------------------------------------------------------------------------
# Rule 5, the two OTHER IPv6 forms that embed an IPv4 address. `resolved.ipv4_mapped`
# unwraps only the IPv4-**mapped** form `::ffff:0:0/96`, so the test above is the only
# embedded-IPv4 shape rule 5 judges by its embedded address. Two more embed one:
#
#   - the **NAT64 well-known prefix** `64:ff9b::/96` (RFC 6052), where
#     `64:ff9b::a9fe:a9fe` embeds `169.254.169.254`, the cloud metadata address;
#   - the deprecated **IPv4-compatible** form `::/96` (RFC 4291), where `::a9fe:a9fe`
#     embeds the same.
#
# `ipaddress` reports `is_global` **true** for either wrapper whatever IPv4 it
# embeds, and `.ipv4_mapped` **None** for both — so a rule that unwraps only the
# mapped form and then asks `is_global` admits an internal IPv4 one address family
# over. On an IPv6-only egress running DNS64/NAT64 a hostile platform's own DNS
# answers a `64:ff9b::`-prefixed AAAA for a fetched host and the gateway translates
# it to the embedded IPv4 — the SSRF rule 5 exists to refuse, arriving through IPv6.
#
# **The fix is to unwrap the embedded IPv4 for these two /96 prefixes and judge THAT,
# exactly as the mapped form is already unwrapped — not to blanket-reject the
# prefixes.** DNS64 legitimately synthesises `64:ff9b::<global-v4>` for a v4-only
# global platform on such a network, so a reject-all rule would refuse a legitimate
# platform. The acceptance rows below are what tell unwrap-and-judge from reject-all:
# a suite of only refusals passes against reject-all, which breaks real DNS64.
#
# A residual limit lives here that no test can pin: a **custom** NAT64 prefix (a
# network-specific prefix rather than the well-known `64:ff9b::/96`) is
# indistinguishable from an ordinary global IPv6 address without the egress's own
# configuration, so it is recorded in the ADR/deferred notes, not asserted here.


def nat64(v4: str) -> str:
    """`64:ff9b::<v4>` — the NAT64 well-known prefix (RFC 6052) embedding `v4`.

    Built from the IPv4 by `ipaddress`, not hand-typed as hex, so the embedded
    address is provably the one the test names rather than a copy that could drift
    from it (`docs/MISTAKES.md` entry 19). Held against its own premises — global
    wrapper, no `ipv4_mapped`, low 32 bits equal to `v4` — by
    `test_the_embedded_ipv4_vectors_sit_where_this_module_claims`.
    """
    from ipaddress import IPv4Address, IPv6Address

    return str(IPv6Address(int(IPv6Address("64:ff9b::")) | int(IPv4Address(v4))))


def ipv4_compatible(v4: str) -> str:
    """`::<v4>` — the deprecated IPv4-compatible form (RFC 4291) embedding `v4`."""
    from ipaddress import IPv4Address, IPv6Address

    return str(IPv6Address(int(IPv4Address(v4))))


# The cloud metadata address the NAT64 attack aims at, and the two internal IPv4s
# that must stay refused however they are embedded. `A_PRIVATE_ADDRESS` is this
# module's own rule-5 constant, held on the non-global side of the line by the
# control at the foot of the file; `A_METADATA_ADDRESS` is link-local and
# non-global for the same reason `169.254.169.254` is refused by rule 4.
A_METADATA_ADDRESS = "169.254.169.254"
EMBEDDED_INTERNAL_ADDRESSES = {
    "the cloud metadata service": A_METADATA_ADDRESS,
    "an RFC 1918 address": A_PRIVATE_ADDRESS,
}

# The two wrappers, as a parameter: a test that named only one would leave the
# other family open, which is exactly the shape of the finding (the mapped form was
# handled and these two were not).
EMBEDDING_PREFIXES = [
    pytest.param(nat64, id="nat64-well-known-prefix"),
    pytest.param(ipv4_compatible, id="ipv4-compatible"),
]


@pytest.mark.parametrize("wrap", EMBEDDING_PREFIXES)
@pytest.mark.parametrize("embedded", list(EMBEDDED_INTERNAL_ADDRESSES))
@pytest.mark.parametrize("column", EVERY_COLUMN)
def test_a_host_resolving_to_an_embedded_internal_ipv4_is_refused_outside_development(
    resolving: Any, column: str, embedded: str, wrap: Any
) -> None:
    """The embedded IPv4 is unwrapped and judged, as the mapped form already is.

    `64:ff9b::a9fe:a9fe` and `::a9fe:a9fe` are `169.254.169.254` reached over an
    IPv6 socket on a DNS64/NAT64 egress, and `ipaddress` reports the wrapper
    `is_global` while its `.ipv4_mapped` is `None`. A rule that unwrapped only the
    mapped form and then asked `is_global` of the wrapper reads a different answer
    from the one the packet gets — which is the exact hazard the mapped-form test
    above closes, in the second and third of the three places that face it
    (`docs/MISTAKES.md` entry 13). Both the metadata address and an RFC 1918 block
    are here because unwrapping has to judge the embedded address itself, not the
    fact that it is embedded, and each is refused on its own account by rule 5.

    Refused on every column, because rule 5's `is_global` refusal has no
    column exemption for these two classes — the only exemption is loopback, which
    is the test after next.

    **The mutation this kills:** rule 5 unwrapping `ipv4_mapped` alone (the state at
    HEAD, which admits both of these). **Its pair** is the boundary acceptance
    below, where the same prefix embedding a global IPv4 is accepted, so this
    cannot be satisfied by refusing every `64:ff9b::` or `::`-prefixed answer.
    """
    wrapped = wrap(EMBEDDED_INTERNAL_ADDRESSES[embedded])
    with pytest.raises(registration_error()):
        judge_with_resolver(
            "production",
            registration(**{column: f"https://{AN_INTERNAL_NAME}/lti/token"}),
            described(resolving, {AN_INTERNAL_NAME: (wrapped,)}),
        )


@pytest.mark.parametrize("wrap", EMBEDDING_PREFIXES)
def test_a_host_resolving_to_an_embedded_loopback_is_refused_on_the_browser_facing_column(
    resolving: Any, wrap: Any
) -> None:
    """The embedded-loopback case, judged the way the module judges resolved loopback.

    `64:ff9b::7f00:1` and `::7f00:1` embed `127.0.0.1`. Unwrapped and judged, that
    is a loopback address, and the module's own split — loopback refused on the
    browser-facing column and admitted on the two this container fetches — is what
    a faithful unwrap produces. So this asserts the refusal on
    `authorization_endpoint`, the column where loopback is always refused, and says
    nothing about the fetched columns: whether a NAT64-wrapped loopback is a
    registrable sidecar is a question the module leaves open exactly as it leaves
    the plain loopback split, and asserting it either way here would settle on the
    implementer's behalf a case no real deployment reaches (a sidecar is dialed at
    `127.0.0.1`, not synthesised through NAT64).

    **The mutation this kills:** the mapped-only unwrap at HEAD, which judges the
    wrapper `is_global` (true) and admits this. **Its pair** is the browser-facing
    loopback refusals in rule 3, which this joins one wrapper out.
    """
    wrapped = wrap(A_LOOPBACK_ADDRESS)
    with pytest.raises(registration_error()):
        judge_with_resolver(
            "production",
            registration(**{AUTHORIZATION_ENDPOINT: f"https://{AN_INTERNAL_NAME}/oidc/authorize"}),
            described(resolving, {AN_INTERNAL_NAME: (wrapped,)}),
        )


@pytest.mark.parametrize("wrap", EMBEDDING_PREFIXES)
@pytest.mark.parametrize("column", EVERY_COLUMN)
def test_a_host_resolving_to_an_embedded_global_ipv4_is_accepted_outside_development(
    resolving: Any, column: str, wrap: Any
) -> None:
    """The boundary that distinguishes unwrap-and-judge from reject-all.

    `64:ff9b::808:808` and `::808:808` embed `8.8.8.8`, a globally routable
    address. This is the DNS64 synthesis a v4-only global platform is legitimately
    reached through on an IPv6-only NAT64 network, so it must be accepted — and a
    fix that blanket-rejected the two prefixes would refuse it while every refusal
    row above stayed green. That is why this row is mandatory rather than
    decorative: a suite of only refusals passes against the reject-all
    implementation that breaks real platforms.

    **This row is green on the current tree, and it is green there by accident:**
    HEAD accepts it because the wrapper's own `is_global` is true, not because it
    judged the embedded `8.8.8.8`. It must stay green after the fix, where it is
    accepted because the embedded address is global. So it does not prove the fix
    by itself — the refusal rows above are what do that — but it is what stops the
    fix from being reject-all.
    """
    wrapped = wrap(ANOTHER_GLOBAL_ADDRESS)
    judge_with_resolver(
        "production",
        registration(**{column: f"https://{AN_INTERNAL_NAME}/lti/token"}),
        described(resolving, {AN_INTERNAL_NAME: (wrapped,)}),
    )


@pytest.mark.parametrize("wrap", EMBEDDING_PREFIXES)
def test_a_fetched_roster_address_resolving_to_an_embedded_internal_ipv4_is_refused(
    resolving: Any, wrap: Any
) -> None:
    """The same shape at the fetched surface, which is where the attack actually lands.

    The roster walk's pagination URL is chosen by the platform at run time and
    judged by `refuse_invalid_fetched_address`, the second entry into the shared
    resolved-address judgment where this finding lives. A hostile `rel="next"` on
    an IPv6-only NAT64 egress names a host whose AAAA is `64:ff9b::a9fe:a9fe`, and
    the gateway translates the GET — with the tool's Bearer token — to the cloud
    metadata service. So the unwrap has to hold on this surface too, not only at the
    registration write.

    **The mutation this kills:** the embedded-IPv4 unwrap threaded into the
    registration function alone, leaving the fetched helper — the surface a platform
    can actually reach — judging the wrapper `is_global`.
    """
    wrapped = wrap(A_METADATA_ADDRESS)
    with pytest.raises(registration_error()):
        judge_fetched(
            "production",
            column=ROSTER_ADDRESS_COLUMN,
            address=f"https://{AN_INTERNAL_NAME}/memberships",
            resolve=resolving({AN_INTERNAL_NAME: (wrapped,)}),
        )


@pytest.mark.parametrize("column", EVERY_COLUMN)
def test_a_host_that_cannot_be_resolved_is_refused_outside_development(
    resolving: Any, column: str
) -> None:
    """Unresolvable is unjudgeable, and unjudgeable is refused.

    The alternative — admitting a host the resolver cannot answer for — is the
    hole the whole rule is walked through: a name that does not resolve at the
    moment of the write resolves to whatever its owner likes at the moment of the
    fetch, and the write-time check has certified it.

    **The mutation this kills:** a `try/except` around the resolution that
    swallows the failure and carries on, which is the natural way to write it and
    which leaves rule 5 doing nothing for exactly the hosts that most need it.
    """
    import socket

    with pytest.raises(registration_error()):
        judge_with_resolver(
            "production",
            registration(**{column: f"https://{AN_UNRESOLVABLE_NAME}/lti/token"}),
            described(resolving, {AN_UNRESOLVABLE_NAME: socket.gaierror("no such host")}),
        )


@pytest.mark.parametrize("column", EVERY_COLUMN)
def test_a_host_that_resolves_to_no_address_at_all_is_refused_outside_development(
    resolving: Any, column: str
) -> None:
    """The second shape of a failed resolution, which raises nothing.

    A resolver can answer "no addresses" without raising — an empty answer
    section, a filtered family — and a rule written as "refuse if it raised"
    admits that silently. Both shapes refuse, and they are separate rows because
    an implementation can close one and leave the other.

    **The mutation this kills:** `if not addresses: return` — which reads as
    "nothing to judge" and is precisely the case that cannot be judged.
    """
    with pytest.raises(registration_error()):
        judge_with_resolver(
            "production",
            registration(**{column: f"https://{AN_EMPTY_ANSWER_NAME}/lti/token"}),
            described(resolving, {AN_EMPTY_ANSWER_NAME: ()}),
        )


@pytest.mark.parametrize(
    "answer",
    [
        pytest.param((A_PRIVATE_ADDRESS,), id="a-private-address"),
        pytest.param((), id="no-address-at-all"),
    ],
)
@pytest.mark.parametrize("column", EVERY_COLUMN)
def test_rule_five_admits_everything_in_development(
    resolving: Any, column: str, answer: tuple[str, ...]
) -> None:
    """The environment pair for the whole of rule 5, on both of its refusals.

    Development admits everything at write time, rule 5 included: ADR 0081's
    decision, unchanged by this batch and stated in its settled design. A
    developer's stack resolves the mock platform to a container address on a
    private network and half the time cannot resolve it at all, and either of the
    two refusals above firing there would stop `make seed` — which takes SPEC
    §14.3's exit criterion with it.

    **The mutation this kills:** rule 5 written outside the environment gate the
    other four sit inside, which passes every refusal in this section.
    """
    judge_with_resolver(
        development_environment(),
        registration(**{column: f"https://{AN_INTERNAL_NAME}/lti/token"}),
        described(resolving, {AN_INTERNAL_NAME: answer}),
    )


@pytest.mark.parametrize("column", EVERY_COLUMN)
def test_a_rule_five_refusal_names_the_column_and_does_not_quote_the_value(
    resolving: Any, column: str
) -> None:
    """The house rule reaches the new rule too: name the column, quote no value.

    Its own row rather than a parameter of the rule 2 message test, because the
    refusal that carries a *resolved address* is the one most likely to be written
    as an f-string — "the host resolved to 10.0.0.7" is the most helpful sentence
    to write and it puts a deployment's internal addressing into a container log
    (SPEC §10) and onto E11's console.

    **The mutation this kills:** a refusal built from the offending address or
    from the addresses it resolved to, and a refusal that names the rule without
    naming the column.
    """
    offending = f"https://{AN_INTERNAL_NAME}/lti/token?tenant={OFFENDING_DETAIL}"
    with pytest.raises(registration_error()) as refusal:
        judge_with_resolver(
            "production",
            registration(**{column: offending}),
            described(resolving, {AN_INTERNAL_NAME: (A_PRIVATE_ADDRESS,)}),
        )

    message = str(refusal.value)
    assert column.lower() in message.lower(), (
        f"The refusal does not name `{column}`: {message!r}. Three columns can carry a refused "
        "address and whoever reads this has to learn which one did."
    )
    assert offending not in message and OFFENDING_DETAIL not in message, (
        f"The refusal quotes the address back: {message!r}. The host is what is being refused and "
        "may be named; the rest is the deployment's own configuration."
    )
    assert A_PRIVATE_ADDRESS not in message, (
        f"The refusal quotes the resolved address back: {message!r}. That is the deployment's "
        "internal addressing, arriving in a log stream and on a rendered console page — the same "
        "rule as the value, one level in, and the one an implementer is most likely to miss "
        "because the sentence is genuinely more helpful with it."
    )


# ---------------------------------------------------------------------------
# Rule 5, at the fetched surface — `refuse_invalid_fetched_address`, the helper
# the roster walk calls once per URL it is about to GET. Two parameters this
# batch adds: `resolve`, and `development_exempt_host`, which is how a
# development stack keeps fetching its own roster without a name lookup while
# still judging anywhere the platform points it.
# ---------------------------------------------------------------------------

A_PLATFORM_HOST = "roster.example.edu"


def fetched(
    environment: str,
    resolve: Any,
    *,
    column: str = ROSTER_ADDRESS_COLUMN,
    host: str = A_PLATFORM_HOST,
    exempt: str | None = None,
) -> Any:
    """One fetched address, spelled `https` so only the rule under test can fire."""
    return judge_fetched(
        environment,
        column=column,
        address=f"https://{host}/memberships",
        resolve=resolve,
        development_exempt_host=exempt,
    )


def test_a_development_stack_does_not_resolve_its_own_roster_host(resolving: Any) -> None:
    """The exemption, and the assertion is that the resolver was **never called**.

    Not "the address was accepted", which is equally true of a development stack
    that resolved the host and liked the answer, and equally true of one where the
    rules do not run at all. The roster walk runs hourly over every section in the
    institution; a name lookup per page, on a stack whose platform is a Compose
    service that half the time resolves to nothing, is a cost and a flake with no
    security value — the operator chose this address.

    **The mutation this kills:** rule 5 running in development for every host,
    with the exemption implemented as "resolve, then forgive" rather than as "do
    not resolve". A test asserting only acceptance cannot tell those apart.
    """
    resolver = resolving({})

    answered = fetched(development_environment(), resolver, exempt=A_PLATFORM_HOST)

    assert not resolver.asked, (
        f"The rules resolved {resolver.asked!r} while judging a development stack's own stored "
        "roster host, which is the one address the exemption is for. Every roster page of every "
        "section would carry that lookup."
    )
    assert answered is None, (
        f"The helper answered {answered!r} where it resolved nothing. The return value is the pin "
        "the sync connects to, and `None` is how it says there is nothing to pin — a tuple here "
        "would have the sync pin an address rule 5 never judged."
    )


@pytest.mark.parametrize(
    "spelling",
    [
        pytest.param("{host}", id="exactly"),
        pytest.param("{host}.", id="one-trailing-dot"),
        pytest.param("{upper}", id="upper-case"),
    ],
)
def test_the_exempt_host_is_compared_the_way_a_resolver_reads_a_host(
    resolving: Any, spelling: str
) -> None:
    """Case-insensitive, with the one-trailing-dot strip ADR 0077 already carries.

    `MOCK-LMS.` and `mock-lms` reach the same service — host names are
    case-insensitive (RFC 4343) and a single trailing dot is the root anchor. A
    comparison that missed either would judge a development stack's own address
    after all, which is the exemption failing in the direction nobody notices: the
    stack still works, and every page costs a lookup.

    **The mutation this kills:** `address_host == development_exempt_host` on the
    raw string. **Its pair** is the next test, where a host the exempt one merely
    prefixes is *not* exempt.
    """
    resolver = resolving({})
    host = spelling.format(host=AN_EXEMPT_HOST, upper=AN_EXEMPT_HOST.upper())

    fetched(development_environment(), resolver, host=host, exempt=AN_EXEMPT_HOST)

    assert not resolver.asked, (
        f"The rules resolved {resolver.asked!r} while judging {host!r} against the exempt host "
        f"{AN_EXEMPT_HOST!r}. The two name the same service."
    )


def test_a_host_the_exempt_one_merely_prefixes_is_judged_and_refused(resolving: Any) -> None:
    """Equality, never a substring — the near miss that decides whether this is a hole.

    `mock-lms.evil.example` is a host somebody else controls, and an exemption
    written as `host.startswith(exempt)` or `exempt in host` hands it the whole of
    rule 5: a platform's `rel="next"` naming it would be fetched with the tool's
    Bearer token, unjudged, on a development stack. That is the same defeat
    `NON_MOCK_URL_SPELLINGS` records for rule 2's catalog, one level out and on
    the permissive side this time.

    **The mutation this kills:** a substring or prefix comparison. **Its pair** is
    the test above, where the host that really is the exempt one is not judged.
    """
    resolver = resolving({A_HOST_THE_EXEMPT_ONE_PREFIXES: (A_PRIVATE_ADDRESS,)})

    with pytest.raises(registration_error()):
        fetched(
            development_environment(),
            resolver,
            host=A_HOST_THE_EXEMPT_ONE_PREFIXES,
            exempt=AN_EXEMPT_HOST,
        )

    assert resolver.asked, (
        "The rules never resolved anything, so the refusal — if there was one — was not rule 5's. "
        f"{A_HOST_THE_EXEMPT_ONE_PREFIXES!r} is not the exempt host and has to be judged."
    )


def test_a_host_that_is_not_the_exempt_one_is_judged_and_accepted_in_development(
    resolving: Any,
) -> None:
    """The pair the refusal above cannot stand without.

    A platform may legitimately page its roster onto a second host of its own, and
    a development stack must still be able to walk it. Without this row, "the
    non-exempt host is judged" is satisfied by a rule that refuses every host that
    is not the exempt one — which stops paging on the demo stack and passes every
    refusal in this section.
    """
    resolver = resolving({A_HOST_THE_EXEMPT_ONE_PREFIXES: (A_GLOBAL_ADDRESS,)})

    answered = fetched(
        development_environment(),
        resolver,
        host=A_HOST_THE_EXEMPT_ONE_PREFIXES,
        exempt=AN_EXEMPT_HOST,
    )

    assert answered == (A_GLOBAL_ADDRESS,), (
        f"The helper answered {answered!r} where it resolved {(A_GLOBAL_ADDRESS,)!r}. The sync "
        "pins the connection to what this returns, so an answer that is not the resolved addresses "
        "either sends the GET somewhere else or leaves it unpinned."
    )


def test_no_exempt_host_in_development_switches_rule_five_off(resolving: Any) -> None:
    """A caller that names no exempt host gets development's blanket admission.

    `provision_from_launch` is that caller: it stores an address out of a launch
    claim and passes neither new argument, so a development stack keeps admitting
    everything at launch time exactly as it did. The rule has to be off rather
    than merely permissive, because there is no address for it to be measured
    against and a lookup on a staff launch buys nothing.

    **The mutation this kills:** `development_exempt_host=None` treated as "no
    host is exempt, so judge everything", which is the reading the name invites
    and which turns every development launch into a DNS lookup that can refuse the
    mock platform's own roster address. **Its pair** is the test above, where the
    identical host and resolver under an exempt host *are* judged and refused.
    """
    resolver = resolving({A_HOST_THE_EXEMPT_ONE_PREFIXES: (A_PRIVATE_ADDRESS,)})

    fetched(
        development_environment(),
        resolver,
        host=A_HOST_THE_EXEMPT_ONE_PREFIXES,
        exempt=None,
    )

    assert not resolver.asked, (
        f"The rules resolved {resolver.asked!r} in development with no exempt host named. Rule 5 "
        "is off there, and a lookup that happens anyway is one a launch pays for."
    )


def test_a_deployment_judges_even_the_stored_roster_host(resolving: Any) -> None:
    """The exemption is development's alone, and a deployment has no such thing.

    The stored address is where the finding lives, not only the pagination URL: a
    registration console writes it, and a launch claim can carry it. Exempting it
    in a deployment would leave the one address an attacker can put there through
    the front door unjudged.

    **The mutation this kills:** the exemption applied wherever it is supplied,
    rather than only under the development name. **Its pair** is the next test,
    where the same exempt host resolving to a public address is accepted, so this
    cannot be satisfied by refusing the exempt host outright.
    """
    resolver = resolving({A_PLATFORM_HOST: (A_PRIVATE_ADDRESS,)})

    with pytest.raises(registration_error()):
        fetched("production", resolver, exempt=A_PLATFORM_HOST)

    assert resolver.asked, (
        "Nothing was resolved, so whatever refused this was not rule 5. A deployment resolves "
        "every fetched address, the section's own included."
    )


def test_a_deployment_accepts_the_stored_roster_host_when_it_resolves_publicly(
    resolving: Any,
) -> None:
    """The pair, and the return value contract at the same time.

    A real institution's roster service is a hostname on a public address, and it
    is fetched hourly. The tuple that comes back is what the sync pins the
    connection to — the address that was judged is the address the GET goes to —
    so an implementation that judged correctly and answered `None` would leave the
    walk re-resolving between the check and the request, which is the rebind this
    batch closes.
    """
    resolver = resolving({A_PLATFORM_HOST: (A_GLOBAL_ADDRESS, ANOTHER_GLOBAL_ADDRESS)})

    answered = fetched("production", resolver, exempt=A_PLATFORM_HOST)

    assert answered == (A_GLOBAL_ADDRESS, ANOTHER_GLOBAL_ADDRESS), (
        f"The helper answered {answered!r} where it resolved "
        f"{(A_GLOBAL_ADDRESS, ANOTHER_GLOBAL_ADDRESS)!r}. The order is the resolver's and the sync "
        "pins the first, so a reordered or truncated answer sends the connection somewhere the "
        "resolver did not put first."
    )


@pytest.mark.parametrize("spelling", list(RESIDUE_LOOPBACK_HOSTS))
def test_a_fetched_roster_address_that_resolves_to_loopback_is_refused(
    resolving: Any, spelling: str
) -> None:
    """ADR 0096's column split, at the fetched surface, through the resolver.

    The roster's pagination URL is chosen by the platform at run time, which is
    why loopback joined link-local on that column and on no other. `127.1` in a
    `Link: rel="next"` header reaches whatever this container is running beside,
    with the tool's Bearer token attached, and it parses as no address at all.

    **The mutation this kills:** the loopback half of rule 5 written against the
    registration function only, leaving the fetched one — the surface a hostile
    platform can actually reach — judging spellings.
    """
    host = RESIDUE_LOOPBACK_HOSTS[spelling]
    with pytest.raises(registration_error()):
        judge_fetched(
            "production",
            column=ROSTER_ADDRESS_COLUMN,
            address=f"https://{host}/memberships",
            resolve=resolving({host: (A_LOOPBACK_ADDRESS,)}),
        )


@pytest.mark.parametrize("spelling", list(RESIDUE_LOOPBACK_HOSTS))
def test_a_fetched_key_set_address_that_resolves_to_loopback_is_admitted(
    resolving: Any, spelling: str
) -> None:
    """The other side of the same split, and the reason it is drawn by column.

    `jwks_url` is written by an operator under their own hand; the roster's next
    page is written by the platform. So the sidecar stays admitted here and is
    refused there, which is ADR 0096's decision and not this batch's to reopen.

    **The mutation this kills:** rule 5 refusing every non-global resolved address
    on every fetched column, which passes the test above and breaks a supported
    deployment. **Its pair** is that test, one column across.
    """
    host = RESIDUE_LOOPBACK_HOSTS[spelling]
    judge_fetched(
        "production",
        column=JWKS_URL,
        address=f"https://{host}/.well-known/jwks.json",
        resolve=resolving({host: (A_LOOPBACK_ADDRESS,)}),
    )


@pytest.mark.parametrize(
    ("label", "answer"),
    [
        pytest.param("raises", None, id="unresolvable"),
        pytest.param("empty", (), id="no-address-at-all"),
    ],
)
def test_a_fetched_address_whose_host_does_not_resolve_is_refused(
    resolving: Any, label: str, answer: Any
) -> None:
    """Both failure shapes, at the surface where the address was chosen at run time.

    A `rel="next"` naming a host that does not resolve is not a page this tool can
    judge, so it is not a page this tool fetches. Two rows because an
    implementation can catch the raise and miss the empty answer.
    """
    import socket

    described_answer = socket.gaierror("no such host") if label == "raises" else answer
    with pytest.raises(registration_error()):
        judge_fetched(
            "production",
            column=ROSTER_ADDRESS_COLUMN,
            address=f"https://{AN_UNRESOLVABLE_NAME}/memberships",
            resolve=resolving({AN_UNRESOLVABLE_NAME: described_answer}),
        )


def test_a_fetched_refusal_names_the_column_and_does_not_quote_the_value(resolving: Any) -> None:
    """The house rule at the fetched surface, where the value came from a platform.

    Sharper here than at the write surface: the refused string was chosen by the
    platform, so quoting it back writes an attacker-supplied value into a
    container log and, through `nrps_call`, onto a console an operator reads —
    which is the second channel E1-11's F1-4 closed for the stored row.
    """
    offending = f"https://{AN_INTERNAL_NAME}/memberships?tenant={OFFENDING_DETAIL}"
    with pytest.raises(registration_error()) as refusal:
        judge_fetched(
            "production",
            column=ROSTER_ADDRESS_COLUMN,
            address=offending,
            resolve=resolving({AN_INTERNAL_NAME: (A_PRIVATE_ADDRESS,)}),
        )

    message = str(refusal.value)
    assert (
        ROSTER_ADDRESS_COLUMN.lower() in message.lower()
    ), f"The refusal does not name `{ROSTER_ADDRESS_COLUMN}`: {message!r}."
    assert (
        offending not in message and OFFENDING_DETAIL not in message
    ), f"The refusal quotes the platform-chosen address back: {message!r}."
    assert A_PRIVATE_ADDRESS not in message, (
        f"The refusal quotes the resolved address back: {message!r}. That is this deployment's "
        "internal addressing, put into a log by a value a platform supplied."
    )


# ---------------------------------------------------------------------------
# Rule 6: the authority that was judged is the authority that will be dialled.
#
# Every rule above reads a host out of `urlsplit(...).hostname`. The client that
# then fetches the address is `requests`, which does not agree with `urlsplit`
# about where an authority ends when the URL carries a raw backslash: WHATWG's
# URL standard treats `\` as a segment terminator and RFC 3986 does not, so
# `https://internal.corp\@public.example/x` is `public.example` with userinfo to
# one of them and `internal.corp` to the other. Judge with the first and connect
# with the second and every rule in this module has been applied to a host the
# packet never goes to — with the tool's Bearer token attached, past the
# resolution pin, and inside whatever network the worker sits in.
#
# The rule is stated as a property rather than as a mechanism: an address whose
# prepared authority differs from its parsed one is refused. That covers the
# backslash and whatever the next disagreement between two parsers turns out to
# be, which a catalog of characters would not (`docs/MISTAKES.md` entry 35).
# ---------------------------------------------------------------------------

# The vector, verified against the installed libraries by the control at the foot
# of this module. Two hosts that both resolve, and both resolve *globally*, so
# that no other rule in this module can be what refuses it: rule 1 is satisfied
# (https), rules 2, 3 and 4 name neither host, and rule 5 accepts both answers.
# The only thing left that can refuse this address is the disagreement itself.
#
# The same string is driven end to end in
# `tests/integration/test_the_roster_sync_refuses_an_address_it_was_told_to_fetch.py`,
# where it arrives in a platform's `Link` header. Two copies of one literal,
# deliberately: the modules share no import path, and a constant that drifted
# would be caught by the control below, which derives both hostnames from the URL
# rather than restating them.
A_JUDGED_HOST = "public.example"
A_DIALLED_HOST = "internal.corp"
AN_AUTHORITY_CONFUSING_URL = f"https://{A_DIALLED_HOST}\\@{A_JUDGED_HOST}/memberships"

# The same address without the backslash: one authority, spelled once, which every
# rule reads the same way. The pair, and the thing a rule that refused too much
# would break.
AN_ORDINARY_FETCHED_URL = f"https://{A_JUDGED_HOST}/memberships"


def test_a_fetched_address_whose_authority_two_parsers_disagree_about_is_refused(
    resolving: Any,
) -> None:
    """The address that is judged as one host and connected to as another.

    **The mutation this kills**: no authority check at all, which is the state at
    HEAD. Every rule in this module reads `urlsplit(...).hostname`, so a `Link:
    rel="next"` carrying this URL is judged as `public.example` — https, globally
    routable, named by no catalog — and `requests` then dials `internal.corp` and
    sends the tool's access token there. It is the ADR 0081 rules defeated one
    level out, not by a spelling they missed but by a parser they never consulted.

    **Both hosts resolve globally**, so no other rule can be what refuses this: a
    refusal here is about the disagreement and nothing else (`docs/MISTAKES.md`
    entry 3 — a test that passes for a reason unrelated to what it asserts).

    **Its pair is the test below**, the same address with one authority, which has
    to keep passing: a rule that refused every URL carrying a character it did not
    like would pass this row and break every ordinary roster.

    What the rule *is* is deliberately left open. Comparing the prepared authority
    with the parsed one is the shape the fix round settled on; refusing the
    character outright, or normalising before judging, would satisfy this test too.
    """
    with pytest.raises(registration_error()):
        judge_fetched(
            "production",
            column=ROSTER_ADDRESS_COLUMN,
            address=AN_AUTHORITY_CONFUSING_URL,
            resolve=resolving(
                {
                    A_JUDGED_HOST: (A_GLOBAL_ADDRESS,),
                    A_DIALLED_HOST: (ANOTHER_GLOBAL_ADDRESS,),
                }
            ),
        )


def test_an_ordinary_fetched_address_with_one_authority_is_still_accepted(
    resolving: Any,
) -> None:
    """The pair: the same host, spelled the way every roster address is spelled.

    **The mutation this kills**: a rule broad enough to refuse an address both
    parsers agree about — the cheapest wrong fix, which passes the refusal above
    and stops every sync in the institution.
    """
    judge_fetched(
        "production",
        column=ROSTER_ADDRESS_COLUMN,
        address=AN_ORDINARY_FETCHED_URL,
        resolve=resolving({A_JUDGED_HOST: (A_GLOBAL_ADDRESS,)}),
    )


# ---------------------------------------------------------------------------
# Rule 6, the second round: the comparison has to be between the two readings,
# not between one reading and itself.
#
# The security re-pass measured the first form of this rule being defeated one
# level out, which is `docs/MISTAKES.md` entry 35's shape arriving for the second
# time on the same rule. The rule ran the *judged* host back through the client's
# own parser before comparing it with the dialled one — so a backslash inside the
# judged host truncated both sides identically, the two agreed, and the address
# was allowed. The exploit the pass measured needs no `@` at all:
#
#     Link: <https://internal.corp\a.evil.example/p2>; rel="next"
#
# `urlsplit` reads the host as `internal.corp\a.evil.example`; `requests` reads
# `internal.corp`. A platform that publishes an A record for
# `internal.corpa.evil.example` gets the judged spelling resolved to its own
# public address by glibc, which escape-processes the backslash — so rules 1 to 5
# all pass, the pin is written under the judged spelling and looked for under the
# dialled one, and the GET carrying the tool's Bearer token goes to
# `internal.corp` inside the deployment's network.
#
# The two forms this section's refusals have to kill are therefore both: *no*
# comparison, and a comparison whose two sides have been put through the same
# parser. What a green here must not cost is the ordinary spellings of a host —
# an IDN, a punycoded label, a trailing dot, a port, userinfo, an IP literal —
# which is what the acceptance rows below are for, one per shape.
# ---------------------------------------------------------------------------

# The measured exploit: a backslash *inside* the host, with no `@` anywhere.
A_TRUNCATED_DIALLED_HOST = "internal.corp"
AN_ESCAPING_JUDGED_HOST = "internal.corp\\a.evil.example"

# A percent-escape of an unreserved character. `urlsplit` leaves it alone and
# `requests` un-escapes it while it re-quotes the URL, so the two readings are two
# different names — a divergence with no backslash in it, which is what says the
# rule is about the disagreement rather than about a character.
A_PERCENT_ESCAPED_JUDGED_HOST = "ex%41mple.com"
A_PERCENT_DECODED_DIALLED_HOST = "example.com"

# Two authorities carrying characters a URL may not contain. Whether `requests`
# reads a second host out of them or refuses to prepare them at all, the tool has
# no business fetching an address whose authority it cannot agree with itself
# about.
A_SPACED_AUTHORITY = "good.example evil.example"
A_QUOTED_AUTHORITY = 'good.example"evil.example'

# Every address whose two readings differ, and every one of them is refused. Each
# is https, names no catalogued host, and resolves globally below, so rule 6 is
# the only rule left that can fire (`docs/MISTAKES.md` entry 3).
DIVERGING_AUTHORITIES = {
    "a backslash inside the judged host": f"https://{AN_ESCAPING_JUDGED_HOST}/memberships",
    "a backslash before an at sign": AN_AUTHORITY_CONFUSING_URL,
    "a percent-escaped letter in the host": f"https://{A_PERCENT_ESCAPED_JUDGED_HOST}/memberships",
    "a space in the authority": f"https://{A_SPACED_AUTHORITY}/memberships",
    "a quotation mark in the authority": f"https://{A_QUOTED_AUTHORITY}/memberships",
}

# What a resolver answers for every host any of the above can be read as, plus the
# background registration's own. All globally routable, so that rule 5 cannot be
# what refuses any of these and a refusal is about the divergence itself.
DIVERGING_RESOLUTIONS = {
    host: (A_GLOBAL_ADDRESS,)
    for host in (
        DEPLOYED_HOST,
        A_JUDGED_HOST,
        A_DIALLED_HOST,
        AN_ESCAPING_JUDGED_HOST,
        A_TRUNCATED_DIALLED_HOST,
        "internal.corpa.evil.example",
        "a.evil.example",
        A_PERCENT_ESCAPED_JUDGED_HOST,
        A_PERCENT_DECODED_DIALLED_HOST,
        A_SPACED_AUTHORITY,
        A_QUOTED_AUTHORITY,
        "good.example",
        "evil.example",
    )
}

# The spellings of one host that are **not** a divergence, one row per shape the
# rule's own docstring names. A host written in a legal but unusual way is an
# ordinary institution's address, and a rule that refused these would refuse
# every platform whose name is not seven ASCII letters — which passes every
# refusal above and is the cheapest wrong fix.
#
# `röster.example` is the one to watch: `requests` IDNA-encodes a non-ASCII host
# while it prepares the URL, so a comparison made between the raw spellings sees
# `röster.example` and `xn--rster-jua.example` and refuses a legitimate address.
# That is what this row exists to catch, and a red on it is a fix that
# over-refuses rather than a broken test.
AN_IDN_HOST = "röster.example"
A_PUNYCODED_HOST = "xn--rster-jua.example"
AN_UNDERSCORED_HOST = "my_host.example"
A_GLOBAL_IPV6_LITERAL = "[2606:4700::1111]"
AN_IPV4_MAPPED_GLOBAL_LITERAL = f"[::ffff:{A_GLOBAL_ADDRESS}]"

ONE_AUTHORITY_SPELLINGS = {
    "a label outside ASCII": f"https://{AN_IDN_HOST}/memberships",
    "the same label punycoded": f"https://{A_PUNYCODED_HOST}/memberships",
    "a single trailing dot": f"https://{A_JUDGED_HOST}./memberships",
    "a port": f"https://{A_JUDGED_HOST}:8443/memberships",
    "userinfo": f"https://tool@{A_JUDGED_HOST}/memberships",
    "mixed case": "https://PuBlic.Example/memberships",
    "an underscore in a label": f"https://{AN_UNDERSCORED_HOST}/memberships",
    "an IPv4 literal": f"https://{A_GLOBAL_ADDRESS}/memberships",
    "an IPv6 literal": f"https://{A_GLOBAL_IPV6_LITERAL}/memberships",
    "an IPv4-mapped IPv6 literal": f"https://{AN_IPV4_MAPPED_GLOBAL_LITERAL}/memberships",
}

ONE_AUTHORITY_RESOLUTIONS = {
    host: (A_GLOBAL_ADDRESS,)
    for host in (A_JUDGED_HOST, AN_IDN_HOST, A_PUNYCODED_HOST, AN_UNDERSCORED_HOST)
}


@pytest.mark.parametrize("shape", sorted(DIVERGING_AUTHORITIES))
def test_every_address_whose_two_readings_differ_is_refused(resolving: Any, shape: str) -> None:
    """Rule 6 as a property, on every divergence the security passes have measured.

    **Two mutations, and the second is the one this round exists for.** The first
    is no comparison at all. The second is **re-preparing the judged host before
    comparing it** — putting both sides through the client's own parser, so that a
    backslash inside the host truncates both readings identically and the rule
    reports agreement about a name the packet will not go to. The row `a backslash
    inside the judged host` is the exploit the security re-pass measured against
    the pinned libraries, and it is allowed by that form of the rule.

    The other rows are the same property reached by other characters: a
    percent-escape the client un-escapes and the parser does not, and two
    authorities carrying characters no URL may contain. None of them is a catalog
    entry — a rule written as "refuse a backslash" passes the first row and fails
    the rest, which is `docs/MISTAKES.md` entry 35 for the third time on this rule.

    **Every host here resolves globally**, so no other rule can be what refuses
    these and a green is about the divergence (`docs/MISTAKES.md` entry 3).

    **A refusal, and specifically a `RegistrationAddressError`.** If an
    `InvalidURL` or a `ValueError` comes out of the chokepoint instead, that is the
    escape the test below this section's next heading is about: the caller catches
    the registration error and nothing else, so an exception from another family
    walks past every handler the walk has.
    """
    with pytest.raises(registration_error()):
        judge_fetched(
            "production",
            column=ROSTER_ADDRESS_COLUMN,
            address=DIVERGING_AUTHORITIES[shape],
            resolve=resolving(DIVERGING_RESOLUTIONS),
        )


@pytest.mark.parametrize("shape", sorted(ONE_AUTHORITY_SPELLINGS))
def test_a_legal_spelling_of_one_authority_is_still_accepted(resolving: Any, shape: str) -> None:
    """The acceptance half, one row per shape a host is legally written in.

    **The mutation this kills**: a rule 6 that compares two spellings which are not
    meant to match — the raw host against the prepared one, where `requests` has
    IDNA-encoded it, stripped the userinfo, or dropped the port. Every one of these
    is one authority written once; refusing any of them stops a real institution
    syncing, and every refusal row above stays green while it happens.

    The IDN rows are the sharp ones. `requests` encodes `röster.example` to
    `xn--rster-jua.example` before it dials, which is *the same host*, and a
    comparison that has not accounted for it reads a legitimate platform as an
    attack. That is a fix that over-refuses, and it is caught here rather than by
    an institution.

    The over-long label is deliberately not in this table: it is refused, for a
    reason that has nothing to do with rule 6 (nothing can resolve it), and the row
    that keeps it honest is `test_a_host_that_cannot_be_resolved_is_refused_
    outside_development` beside a `RegistrationAddressError` requirement in the
    next section.
    """
    judge_fetched(
        "production",
        column=ROSTER_ADDRESS_COLUMN,
        address=ONE_AUTHORITY_SPELLINGS[shape],
        resolve=resolving(ONE_AUTHORITY_RESOLUTIONS),
    )


@pytest.mark.parametrize("column", FETCHED_COLUMNS)
def test_a_registration_address_whose_two_readings_differ_is_refused(
    resolving: Any, column: str
) -> None:
    """Rule 6 on the columns written at registration, not only on the fetched one.

    **The mutation this kills**: rule 6 applied to `refuse_invalid_fetched_address`
    alone. The deferral that left it there assumed rule 5 backstops these columns,
    and it does not: `https://10.0.0.5\\@public.example/jwks` is judged *and
    resolved* as `public.example`, which is globally routable and passes, while the
    client dials `10.0.0.5`. The private address never appears to the rule that
    exists to refuse private addresses.

    **Why these two columns and why it is credential exposure.** `auth_token_url`
    is where `pylti1p3` posts the tool's signed client assertion — an assertion
    audienced at that URL, sent to whatever host the client resolves out of it. A
    registration written with one of these addresses hands a signed credential to
    the authority nobody judged, on every token request, for as long as the row
    lives. `jwks_url` decides which keys may sign an accepted launch, which is the
    signing oracle ADR 0077 closed for the web door.

    `authorization_endpoint` is deliberately not asserted, the same stance this
    module takes on rule 4: it is a browser-facing string that this container never
    fetches, so the argument that closes these two does not reach it, and answering
    it here would settle a question the ticket leaves open.
    """
    with pytest.raises(registration_error()):
        judge(
            "production",
            registration(**{column: AN_AUTHORITY_CONFUSING_URL}),
            resolve=resolving(DIVERGING_RESOLUTIONS),
        )


@pytest.mark.parametrize("column", FETCHED_COLUMNS)
def test_an_ordinary_registration_address_is_still_accepted(resolving: Any, column: str) -> None:
    """The pair for the two columns above: the registration a real institution writes.

    **The mutation this kills**: rule 6 widened until it refuses an address both
    parsers agree about, which passes both refusals above and makes every platform
    unregistrable. The background registration is the one every other acceptance
    row in this module rests on.
    """
    judge(
        "production",
        registration(**{column: f"https://{A_JUDGED_HOST}/lti/token"}),
        resolve=resolving(DIVERGING_RESOLUTIONS),
    )


# ---------------------------------------------------------------------------
# The exception family: a fetched address may be refused, and may not raise
# something the caller does not catch.
#
# Rule 5's own comment claims this family closed. The security re-pass found a
# third member: an authority carrying `[` or `]` makes `urlsplit` raise
# `ValueError: Invalid IPv6 URL` out of the host reader, which is not a
# `RegistrationAddressError`. The walk catches the registration error; a
# `ValueError` goes past it to the per-section handler, the savepoint rolls back,
# no `nrps_call` row is written, and every member already read is discarded. One
# `Link` header erases a section's sync record and its audit trail.
# ---------------------------------------------------------------------------

# An authority a URL parser cannot read at all. Refused, and refused *as this
# family's own error*, which is the whole of the finding.
A_BRACKETED_AUTHORITY = "a]b.example"
AN_UNPARSEABLE_URL = f"https://{A_BRACKETED_AUTHORITY}/memberships"


def test_an_address_whose_authority_cannot_be_parsed_is_refused_as_a_registration_error(
    resolving: Any,
) -> None:
    """The refusal has to arrive in the family the callers catch.

    **The mutation this kills**: letting the host reader's `ValueError` out of the
    chokepoint. `pytest.raises(registration_error())` is what catches it — a bare
    `ValueError` is not an instance of the registration error, whatever the
    registration error inherits from, so this row goes red on the escape rather
    than swallowing it. The walk's half of the same finding is asserted where the
    walk is, because a chokepoint that refuses correctly and a caller that catches
    the wrong class are two different defects with the same symptom.

    A caller that catches `RegistrationAddressError` and nothing else is not
    written wrongly: the chokepoint's contract is that it returns or raises that
    one class. An exception of another family means the contract has a hole, and
    the hole costs a section its whole sync record rather than one page.
    """
    with pytest.raises(registration_error()):
        judge_fetched(
            "production",
            column=ROSTER_ADDRESS_COLUMN,
            address=AN_UNPARSEABLE_URL,
            resolve=resolving({A_BRACKETED_AUTHORITY: (A_GLOBAL_ADDRESS,)}),
        )


# ---------------------------------------------------------------------------
# Controls. Two constants decide most of this module, and a stale one refuses
# nothing while reporting exactly what a correct one reports (`docs/MISTAKES.md`
# entry 35). **A red in this section means these tests are broken, not the code.**
# Nothing here imports the application except the last rows, which read
# already-shipped constants.
# ---------------------------------------------------------------------------


def test_the_two_url_parsers_disagree_about_this_modules_authority_vector() -> None:
    """A control: the vector really is read as two different hosts by the two readers.

    Everything rule 6 asserts rests on a claim about two libraries — that
    `urlsplit` sees `public.example` where `requests` sees `internal.corp`. If a
    version of either ever agreed with the other, the refusal above would still
    pass (a rule can refuse an address for any reason) while the thing it was
    written to stop had ceased to exist, and nobody would know. That is
    `docs/MISTAKES.md` entry 9 with the evidence removed.

    So both readings are taken here, from the same string, and required to differ
    and to be the two hosts this module names. `PreparedRequest.prepare_url` is
    exactly what `requests.Session.send` will have done to the URL before it dials.

    **A red here means the vector has moved, not that the code is wrong** — and a
    moved vector needs the security finding re-verified rather than the test
    relaxed.
    """
    from urllib.parse import urlsplit

    from requests.models import PreparedRequest

    parsed = urlsplit(AN_AUTHORITY_CONFUSING_URL).hostname
    prepared = PreparedRequest()
    prepared.prepare_url(AN_AUTHORITY_CONFUSING_URL, None)
    dialled = urlsplit(str(prepared.url)).hostname

    assert parsed == A_JUDGED_HOST, (
        f"`urlsplit` reads {AN_AUTHORITY_CONFUSING_URL!r} as host {parsed!r} and this module's "
        f"rules are written as though it read {A_JUDGED_HOST!r}. Every other assertion about this "
        "vector describes a judgment that is not being made."
    )
    assert dialled == A_DIALLED_HOST, (
        f"`requests` prepares {AN_AUTHORITY_CONFUSING_URL!r} as {prepared.url!r}, whose host is "
        f"{dialled!r} rather than {A_DIALLED_HOST!r}. The finding is that the judged host and the "
        "dialled host differ; if they no longer do, this vector is no longer a vector and the "
        "refusal above is protecting against nothing."
    )
    assert parsed != dialled, (
        f"Both readers agree that {AN_AUTHORITY_CONFUSING_URL!r} names {parsed!r}, so there is no "
        "authority confusion here at all."
    )


# The two rows whose readings the security re-pass measured by name. The rest of
# `DIVERGING_AUTHORITIES` is required only to *diverge*, because whether the
# client reads a second host out of a space or refuses to prepare the URL at all
# is the client's business and either answer makes the address one this tool must
# not fetch.
NAMED_AUTHORITY_READINGS = {
    "a backslash inside the judged host": (AN_ESCAPING_JUDGED_HOST, A_TRUNCATED_DIALLED_HOST),
    "a percent-escaped letter in the host": (
        A_PERCENT_ESCAPED_JUDGED_HOST,
        A_PERCENT_DECODED_DIALLED_HOST,
    ),
    "a backslash before an at sign": (A_JUDGED_HOST, A_DIALLED_HOST),
}


@pytest.mark.parametrize("shape", sorted(DIVERGING_AUTHORITIES))
def test_every_vector_in_the_diverging_table_really_diverges(shape: str) -> None:
    """A control: each refusal row above is a divergence against the installed libraries.

    A refusal test proves nothing about a vector that is not one. If a version of
    either parser ever agreed with the other about one of these strings, that row
    would keep passing — a rule may refuse an address for any reason — while the
    thing it was written to stop had quietly ceased to exist. That is
    `docs/MISTAKES.md` entry 9 with the evidence removed, and it is why every row
    is measured here rather than argued for.

    The measurement is: what `urlsplit` reads as the host, and what
    `PreparedRequest.prepare_url` — the exact call `requests.Session.send` makes
    before it dials — leaves behind. They must differ, or the client must refuse to
    prepare the URL at all, which is the same conclusion by a shorter route.

    The three rows whose two readings the security passes named are checked against
    those names as well, so a vector that starts diverging into some *third* host
    is reported rather than accepted as still-a-divergence.

    **A red here means a vector has moved, not that the code is wrong.**
    """
    from urllib.parse import urlsplit

    from requests.exceptions import InvalidURL
    from requests.models import PreparedRequest

    url = DIVERGING_AUTHORITIES[shape]
    judged = urlsplit(url).hostname
    assert judged, f"`urlsplit` reads no host at all out of {url!r}, so nothing here is judged."

    prepared = PreparedRequest()
    try:
        prepared.prepare_url(url, None)
    except (InvalidURL, UnicodeError, ValueError):
        dialled = None
    else:
        dialled = urlsplit(str(prepared.url)).hostname

    assert dialled is None or dialled != judged, (
        f"Both readers agree that {url!r} names {judged!r}. This row is in the refusal table as a "
        "divergence and it is not one any more — the refusal above may still pass, and it is no "
        "longer evidence of anything."
    )
    named = NAMED_AUTHORITY_READINGS.get(shape)
    if named is not None:
        assert (judged, dialled) == named, (
            f"{url!r} is read as {(judged, dialled)!r} and the security pass measured "
            f"{named!r}. The vector has changed shape; re-verify the finding before trusting the "
            "refusal that rests on it."
        )


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


def test_the_address_vectors_sit_on_the_side_of_is_global_this_module_claims() -> None:
    """A control: rule 5 is `is_global`, so a vector on the wrong side inverts a test.

    This is the trap the batch's own work order names, and it is invisible in the
    test that trips over it: `203.0.113.10` (TEST-NET-3) and `192.0.2.1`
    (TEST-NET-1) read like public addresses and are reserved, so `is_global` is
    false for both. A refusal test using one is green for the wrong reason, and an
    acceptance test using one is red for the wrong reason — and this module used
    TEST-NET-3 as its "not loopback, not private" literal until rule 5 arrived.

    Arithmetic on `ipaddress` and this module's own constants, which is why it can
    be relied on to say something about the rest.
    """
    from ipaddress import ip_address

    for address in (A_GLOBAL_ADDRESS, ANOTHER_GLOBAL_ADDRESS, NON_LOOPBACK_IP_LITERAL):
        assert ip_address(address).is_global, (
            f"This module uses {address!r} as an ordinary public address, and `ipaddress` reports "
            "it is not globally routable. Every acceptance row built on it is asserting the "
            "opposite of what it says."
        )
    for address in ("203.0.113.10", "192.0.2.1"):
        assert not ip_address(address).is_global, (
            f"{address!r} is globally routable on this interpreter, so the documentation ranges "
            "would be usable here after all and this control's premise is stale."
        )
    for address in (A_PRIVATE_ADDRESS, A_LOOPBACK_ADDRESS):
        assert not ip_address(address).is_global, (
            f"This module uses {address!r} as an address rule 5 refuses, and `ipaddress` reports "
            "it is globally routable. Every refusal row built on it would be asserting nothing."
        )
    for spelling, host in PRIVATE_URL_HOSTS.items():
        assert not ip_address(host.strip("[]")).is_global, (
            f"`PRIVATE_URL_HOSTS[{spelling!r}]` is {host!r}, which is globally routable — so the "
            "refusal rows built on it are about an address rule 5 accepts."
        )


def test_the_embedded_ipv4_vectors_sit_where_this_module_claims() -> None:
    """A control: the NAT64 and IPv4-compatible vectors are what the finding describes.

    Every embedded-IPv4 test above rests on three facts about `ipaddress`, and if
    any were false the test would be green or red for a reason unrelated to what it
    asserts (`docs/MISTAKES.md` entry 3):

      - the **wrapper** is judged `is_global` true — this is *why* the mapped-only
        unwrap at HEAD admits it, and the reason the refusal rows are red today;
      - the wrapper's `.ipv4_mapped` is `None` — this is *why* the existing unwrap
        walks past it, so the fix cannot lean on the attribute it already reads;
      - the low 32 bits equal the IPv4 the vector names — this is what
        unwrap-and-judge reads, so a fix that read the wrong bits would confuse a
        prefix embedding a global address with one embedding an internal one.

    And the embedded IPv4s themselves sit on the side of `is_global` the tests
    need: the metadata, RFC 1918 and loopback addresses are non-global (refused
    once unwrapped) and `8.8.8.8` is global (accepted once unwrapped). Arithmetic
    on `ipaddress` and this module's own constants, green today and after the fix —
    the fix changes the rule, not the standard library.
    """
    from ipaddress import IPv4Address, ip_address

    internal = (A_METADATA_ADDRESS, A_PRIVATE_ADDRESS, A_LOOPBACK_ADDRESS)
    for wrap in (nat64, ipv4_compatible):
        for v4 in (*internal, ANOTHER_GLOBAL_ADDRESS):
            wrapped = ip_address(wrap(v4))
            assert wrapped.is_global, (
                f"{wrap.__name__}({v4!r}) is {wrapped!r}, which `ipaddress` does not report "
                "globally routable — so the mapped-only unwrap at HEAD would refuse it already "
                "and the refusal rows built on it prove nothing about the embedded-IPv4 fix."
            )
            assert wrapped.ipv4_mapped is None, (
                f"{wrap.__name__}({v4!r}) is {wrapped!r}, whose `.ipv4_mapped` is "
                f"{wrapped.ipv4_mapped!r} rather than None — so the existing unwrap would catch it "
                "and this whole section is about a case the code already handles."
            )
            assert IPv4Address(int(wrapped) & 0xFFFFFFFF) == IPv4Address(v4), (
                f"{wrap.__name__}({v4!r}) is {wrapped!r}, whose low 32 bits are "
                f"{IPv4Address(int(wrapped) & 0xFFFFFFFF)!r} rather than {v4!r} — so a fix that "
                "unwrapped the low 32 bits would judge an address this vector does not embed."
            )
    for v4 in internal:
        assert not IPv4Address(v4).is_global, (
            f"{v4!r} is globally routable, so the refusal rows that embed it are about an address "
            "rule 5 accepts once it is unwrapped."
        )
    assert IPv4Address(ANOTHER_GLOBAL_ADDRESS).is_global, (
        f"{ANOTHER_GLOBAL_ADDRESS!r} is not globally routable, so the boundary acceptance built on "
        "it would be asserting the opposite of what it says."
    )


def test_the_residue_spellings_parse_as_no_address_at_all() -> None:
    """A control: the residue vectors are residue, rather than addresses in disguise.

    Every one of ADR 0081's four residue spellings is here because
    `ipaddress.ip_address` refuses it — that is what makes rules 3 and 4 blind to
    them and what makes a resolver the only fix. If any of them started parsing,
    the rule-5 test built on it would be green against a rule that never resolved
    anything, which is `docs/MISTAKES.md` entry 3 exactly.
    """
    from ipaddress import ip_address

    for spelling, host in RESIDUE_LOOPBACK_HOSTS.items():
        with pytest.raises(ValueError):
            ip_address(host)
        assert host, f"`RESIDUE_LOOPBACK_HOSTS[{spelling!r}]` is empty."


def test_the_fetched_columns_split_on_loopback_the_way_this_module_drives_them() -> None:
    """A control: this module's two fetched columns are the ones the code splits on.

    `docs/MISTAKES.md` entry 35's shape — a guard that only ever reports absence
    cannot tell you which mechanisms it can see. Every fetched-surface test above
    asserts that the roster column refuses a resolved loopback address and that
    `jwks_url` admits one, and both halves are satisfied by column names the
    module under test has never heard of: a refusal for the wrong reason on one
    side and no rule at all on the other.

    So both tuples are read from `app.models.lti` and each column is *found* in
    the one it belongs to, rather than merely missing from the other.
    """
    from app.models.lti import FETCHED_COLUMNS as CODE_FETCHED
    from app.models.lti import LOOPBACK_REFUSED_COLUMNS as CODE_LOOPBACK_REFUSED

    assert ROSTER_ADDRESS_COLUMN in CODE_FETCHED, (
        f"`{ROSTER_ADDRESS_COLUMN}` is not among the fetched columns {tuple(CODE_FETCHED)}, so the "
        "roster-address tests above are driving a column the rules do not judge."
    )
    assert ROSTER_ADDRESS_COLUMN in CODE_LOOPBACK_REFUSED, (
        f"`{ROSTER_ADDRESS_COLUMN}` is not among {tuple(CODE_LOOPBACK_REFUSED)}, so the loopback "
        "refusal asserted for it is asserting something ADR 0096 does not say."
    )
    assert (
        JWKS_URL in CODE_FETCHED
    ), f"`{JWKS_URL}` is not among the fetched columns {tuple(CODE_FETCHED)}."
    assert JWKS_URL not in CODE_LOOPBACK_REFUSED, (
        f"`{JWKS_URL}` is among {tuple(CODE_LOOPBACK_REFUSED)}, so ADR 0096's split has moved and "
        "the sidecar acceptance above contradicts it."
    )


@pytest.mark.parametrize("column", (AGS_LINE_ITEMS_COLUMN, AGS_LINE_ITEM_COLUMN))
def test_both_gradebook_columns_are_judged_and_refuse_loopback(column: str) -> None:
    """E3-02 criterion 2: the enumerations cannot quietly shrink.

    > The new address column appears in `FETCHED_COLUMNS` and
    > `LOOPBACK_REFUSED_COLUMNS`, and whatever test pins those enumerations fails if
    > the column is dropped from either.

    This is that test, and it is here rather than in a module of its own because
    this file is where those two tuples are already pinned — a second home for the
    same rule would be two records of one fact, and one of them would go stale
    (`docs/MISTAKES.md` entry 19).

    **Both tuples, and each does a different job.** `FETCHED_COLUMNS` is what makes
    an address judged at all: E3-04 lists and creates line items in the container,
    and E3-05 and E3-06 post scores to the line item, both with the tool's own
    client credentials attached and nobody present — the same SSRF surface the
    roster address is, arriving through a different claim.
    `LOOPBACK_REFUSED_COLUMNS` is the narrower rule ADR 0096 draws: a key-set
    sidecar on `127.0.0.1` is an ordinary deployment and stays legal on `jwks_url`,
    while an address a *platform chooses at run time* may not name this machine.
    Both gradebook addresses are chosen by the platform — one advertised in a
    claim, one returned by the platform when a line item is created — so both are on
    the refusing side of that split.

    **The mutation this kills:** either column dropped from either tuple, which is
    `docs/MISTAKES.md` entry 35's shape — a guard that enumerates the things it
    covers, quietly missing one. A column absent from `FETCHED_COLUMNS` is not
    judged at all; a column absent from `LOOPBACK_REFUSED_COLUMNS` is judged and
    admits `http://127.0.0.1:9999/lineitems` out of a launch claim.

    **The behaviour behind this pin** is the loopback pair in
    `tests/integration/test_a_launch_stores_the_gradebook_address_it_was_given.py`,
    which drives a loopback container address through the writer and requires it
    refused. A membership assertion on its own would be satisfied by a tuple nobody
    reads; that module is what says the tuple is consulted.

    **The control beside it** is the test above, which finds the roster column in
    both tuples and `jwks_url` in exactly one — so a red here is a statement about
    these two columns rather than about a build whose tuples are empty.
    """
    from app.models.lti import FETCHED_COLUMNS as CODE_FETCHED
    from app.models.lti import LOOPBACK_REFUSED_COLUMNS as CODE_LOOPBACK_REFUSED

    assert (
        ROSTER_ADDRESS_COLUMN in CODE_FETCHED and ROSTER_ADDRESS_COLUMN in CODE_LOOPBACK_REFUSED
    ), (
        f"`{ROSTER_ADDRESS_COLUMN}` is not in both tuples — fetched {tuple(CODE_FETCHED)}, "
        f"loopback-refused {tuple(CODE_LOOPBACK_REFUSED)}. That column has been in both since ADR "
        "0096, so this is a build whose enumerations are not what this file thinks they are, and "
        "the assertions below would be about a tuple that means something else."
    )
    assert column in CODE_FETCHED, (
        f"`{column}` is not among the fetched columns {tuple(CODE_FETCHED)}. E3-02 stores it on "
        "`section` and E3-04 fetches it with the tool's own client credentials, on a schedule, "
        "with nobody watching — so a column outside this tuple is an address that reaches the "
        "database without being judged at all, which is the hole the roster address had until a "
        "security review found it."
    )
    assert column in CODE_LOOPBACK_REFUSED, (
        f"`{column}` is not among {tuple(CODE_LOOPBACK_REFUSED)}, so a launch claim naming "
        "`http://127.0.0.1:9999/lineitems` is stored and later fetched with a Bearer token "
        "attached. ADR 0096's split admits loopback on the columns an *operator* writes and "
        "refuses it on the ones a *platform* chooses at run time, and both gradebook addresses are "
        "the platform's."
    )


def test_this_modules_address_vectors_are_the_ones_the_wire_tests_drive(
    roster_contract: Any,
) -> None:
    """A control: the unit and integration halves of rule 5 judge the same addresses.

    The pin tests over the wire drive `roster_contract`'s vectors and the rules
    here drive this module's. Two copies of the same three addresses is
    `docs/MISTAKES.md` entry 19's shape — a test holding its expectation in a copy
    of the thing it is checking — and the failure it produces is the worst kind: a
    green unit suite about `10.0.0.7` and a green wire suite about an address that
    drifted onto the other side of `is_global`.
    """
    assert (roster_contract.a_global_address, roster_contract.a_private_address) == (
        A_GLOBAL_ADDRESS,
        A_PRIVATE_ADDRESS,
    ), (
        "The wire tests drive "
        f"{(roster_contract.a_global_address, roster_contract.a_private_address)!r} and this "
        f"module drives {(A_GLOBAL_ADDRESS, A_PRIVATE_ADDRESS)!r}."
    )
