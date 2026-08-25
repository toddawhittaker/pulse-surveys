"""The identity provider is configured per deployment, and the mock is refused outside it.

Ticket E0-39, and the epic-boundary threat model that raised it. `app.config`
defaulted `OIDC_ISSUER` to `http://mock-idp:8000`, the token endpoint and the key
set to addresses on the same service, and `OIDC_CLIENT_ID` to `mock-idp-client`,
while the base Compose file starts `mock-idp` in every deployment. An operator who
deploys per SPEC §7.2 and sets none of those variables has deployed a signing
oracle for fake CARE and ADMIN identities, which this tool then verifies correctly
and trusts. ADR 0075 chose those defaults deliberately; ADR 0077 reverses that half
of them.

Three layers: the ticket's two, and a third the security review added. The tests
below are in matching sections.

**The five settings are required.** `oidc_issuer`, `oidc_authorization_endpoint`,
`oidc_token_endpoint`, `oidc_jwks_url` and `oidc_client_id` lose their defaults, so
a deployment that supplies no identity provider stops at startup with
`app.config.ConfigurationError` naming the missing field — the refusal E0-01
criterion 2 already gives every other deployment-specific variable. Where the
development values live instead is the subject of two sibling modules:
`tests/unit/test_compose_stack.py` holds the api service's Compose environment and
`tests/unit/test_env_example_resolves.py` holds `.env.example`.

**A mock address is refused outside development.** Two spellings, and they are the
subject of the rule rather than an incidental pair, so they are named here the way
`test_compose_stack.py` names `SUPERUSER_VARIABLES` rather than derived: the
Compose **service name** `mock-idp`, which is how a container on this stack reaches
the mock, and the mock's **registered client id** `mock-idp-client`, which is how a
configuration names the mock without addressing it. `localhost` is deliberately not
in *this* catalog — inside a deployed container it cannot resolve to the mock — and
that is ADR 0077's to justify, not this module's to widen. It is refused on one
field for an unrelated reason, which is the third layer below.

**The host component, compared exactly.** The ticket says "any `oidc_*` URL whose
host is `mock-idp`", and this module pins what "is" means: the URL's parsed host,
equal to the service name, rather than the service name appearing anywhere in the
URL. A substring rule would refuse `https://mock-idp.example.edu/oidc/token` — a
perfectly ordinary institutional address for a real provider — and would also fire
on a *path* segment, which addresses nothing. Both directions are asserted, in
pairs, so neither reading can be satisfied by accident.

**A configuration can reach the same outcome without naming the mock**, which is
what the security review of this ticket went looking for and found three of. Each
is a rule of its own in the last section: the browser-facing endpoint may not point
at the end user's own machine (a local listener becomes a phishing page on an
institution-issued link, and that rule closes over the loopback *class* rather than
a list of spellings — the finding arrived with a fourth spelling already in it); an
`oidc_*` URL may not be cleartext to another host
outside development (an on-path answer to the key-set fetch is the same signing
oracle, reached without the mock); and the parsed host is normalised for one
trailing dot before every catalog comparison, because `mock-idp.` resolves exactly
as `mock-idp` does. The first two are MEDIUM, the third LOW.

**Every refusal is paired with an acceptance.** A validator that refuses
everything outside development, or that refuses the development stack too, passes
every refusal test here and closes both doors; the pairs are what stop that. The
sharpest of them is
`test_the_development_stack_configuration_is_accepted_in_development` — the whole
of E0's §14.3 exit criterion is that `docker compose up` from a clean checkout
reaches a system a person can log in to.

**Which failure a red here is.** Several tests are marked as controls in their
docstrings: they must be green today, before any of this is implemented, and a red
one means the machinery here is broken rather than that the configuration is. Every
acceptance row is in the same position — it passes today because nothing refuses
anything yet, and its whole value is that it must still pass afterwards. Everything
else is expected red until the ticket lands, on an assertion or on `DID NOT RAISE`,
never on an import: `Settings`, `ConfigurationError` and `DEVELOPMENT_ENVIRONMENT`
all exist already.

**Every refusal in the last section is written so that exactly one rule can be what
fires** — the loopback and trailing-dot rows carry `https` so the transport rule
cannot be the refusal — and where two rules genuinely overlap there is a test that
says so by name. A refusal test that passes because some other rule fired is green
for a reason unrelated to what it asserts (`docs/MISTAKES.md` entry 3), and with
three rules over five fields that is the failure mode here rather than a
hypothetical.
"""

from collections.abc import Mapping
from urllib.parse import urlsplit

import pytest

# The variable each setting arrives in. **These spellings are not this module's
# choice** — `tests/fixtures/doors.py` already fixes them for E0-18's door suites, and
# `.env.example` documents all five — so they are transcribed rather than decided,
# and a rename is these five lines plus that fixture.
OIDC_ISSUER_VARIABLE = "OIDC_ISSUER"
OIDC_AUTHORIZATION_ENDPOINT_VARIABLE = "OIDC_AUTHORIZATION_ENDPOINT"
OIDC_TOKEN_ENDPOINT_VARIABLE = "OIDC_TOKEN_ENDPOINT"  # noqa: S105
OIDC_JWKS_URL_VARIABLE = "OIDC_JWKS_URL"
OIDC_CLIENT_ID_VARIABLE = "OIDC_CLIENT_ID"

# The four that are URLs, and the five that are required. The split matters: the
# host rule below reads a URL, and the client id is not one, so a rule phrased over
# "every `oidc_*` setting whose host is the mock" silently covers four of five.
OIDC_URL_VARIABLES = (
    OIDC_ISSUER_VARIABLE,
    OIDC_AUTHORIZATION_ENDPOINT_VARIABLE,
    OIDC_TOKEN_ENDPOINT_VARIABLE,
    OIDC_JWKS_URL_VARIABLE,
)
REQUIRED_OIDC_VARIABLES = (*OIDC_URL_VARIABLES, OIDC_CLIENT_ID_VARIABLE)

ENVIRONMENT_VARIABLE = "ENVIRONMENT"

# The two spellings by which a configuration can reach or name the mock, named
# here rather than derived. Deriving them is what reads as a rule and is a list of
# two — "the service whose image is built from `mock-idp/`" names the same thing one
# step further away — and a third spelling belongs in a reviewed diff on this line.
#
# Both are held against reality by controls at the end of this module rather than
# by trust: `mock-idp` is compared with the `mock_idp_service` fixture, and
# `mock-idp-client` with what `.env.example` actually configures. A catalog that
# has gone stale refuses nothing and reports the same clean result as a catalog
# that is right (`docs/MISTAKES.md` entry 35).
MOCK_SERVICE = "mock-idp"
MOCK_CLIENT_ID = "mock-idp-client"

# A provider that is not the mock, for every test that needs a configuration a real
# deployment could hold. `.example.edu` resolves nowhere, which is the point: these
# values are never fetched by anything here.
DEPLOYED_HOST = "idp.example.edu"
DEPLOYED_OIDC = {
    OIDC_ISSUER_VARIABLE: f"https://{DEPLOYED_HOST}",
    OIDC_AUTHORIZATION_ENDPOINT_VARIABLE: f"https://{DEPLOYED_HOST}/oidc/authorize",
    OIDC_TOKEN_ENDPOINT_VARIABLE: f"https://{DEPLOYED_HOST}/oidc/token",
    OIDC_JWKS_URL_VARIABLE: f"https://{DEPLOYED_HOST}/.well-known/jwks.json",
    OIDC_CLIENT_ID_VARIABLE: "pulse-surveys-at-example-edu",
}

# Environments that are not the development one, written as templates because the
# development name is read from `app.config` rather than spelled here (E0-37 item 2
# makes that its single definition site) and parametrisation needs a value at
# collection time.
#
# The last two rows are the near miss that matters: a rule written as
# `DEVELOPMENT_ENVIRONMENT in settings.environment` passes every other row here and
# hands `staging-development` the mock. `tests/integration/test_demo_seed_script.py`
# carries the same row against the seed's own gate, for the same reason.
NON_DEVELOPMENT_ENVIRONMENTS = (
    "production",
    "staging",
    "{development}-blue",
    "pre-{development}",
)

# Mock addresses, one per spelling, because a rule that reads the development
# stack's exact string is not a rule about the host. The port is not part of the
# question — a container reaching `mock-idp` on any port reaches the mock — and
# neither is the scheme or the path.
MOCK_URL_SPELLINGS = {
    "the development stack's own value": f"http://{MOCK_SERVICE}:8000/oidc/token",
    "no port": f"http://{MOCK_SERVICE}/oidc/token",
    "https on another port": f"https://{MOCK_SERVICE}:8443/oidc/token",
    "no path": f"http://{MOCK_SERVICE}:8000",
    "a query string": f"http://{MOCK_SERVICE}:8000/oidc/token?prompt=login",
}

# The other direction: URLs that contain the service name and do not address the
# mock. Each is a real address someone could deploy, and each is refused by the
# substring rule that is the obvious way to write the check above.
NON_MOCK_URL_SPELLINGS = {
    "the service name as a subdomain": f"https://{MOCK_SERVICE}.example.edu/oidc/token",
    "a host the service name prefixes": f"https://{MOCK_SERVICE}-2.example.edu/oidc/token",
    "a host the service name ends": f"https://staging-{MOCK_SERVICE}/oidc/token",
    "the service name in the path": f"https://{DEPLOYED_HOST}/{MOCK_SERVICE}/oidc/token",
}

# The same pair for the client id, which is compared as a whole value and not as a
# fragment of one.
NON_MOCK_CLIENT_IDS = {
    "a longer id the mock's ends": f"pulse-{MOCK_CLIENT_ID}",
    "a longer id the mock's begins": f"{MOCK_CLIENT_ID}-2",
}

# ---------------------------------------------------------------------------
# The security review's three findings. Constants here; the tests are in their own
# section at the end of the module.
# ---------------------------------------------------------------------------

# **The loopback refusal is a class, not a list of spellings.**
#
# The first version of this constant was three literals — `localhost`, `127.0.0.1`,
# `[::1]` — and the round that wrote it noticed a fourth spelling on the way past.
# That is the shape this epic keeps meeting: a closed-set guard defeated one level
# further out each round. A three-entry catalog does not invite the fifth spelling,
# it waits for it. `http://127.0.0.2:8081/authorize` and
# `http://[::ffff:127.0.0.1]:8081/authorize` each send a browser to a listener on the
# user's own machine, and neither is in a three-entry list.
#
# So the rule pinned below is a class: the parsed host is `localhost` — case-folded,
# one trailing dot stripped — **or** it is an IP literal that `ipaddress` calls
# loopback, which is the whole of `127.0.0.0/8`, `::1`, and the IPv4-mapped
# `::ffff:127.0.0.1` — measured on Python 3.13, this repository's floor, that last
# one answers `is_loopback` directly, and `ipv4_mapped` is the version-portable
# route to the same answer rather than the only one.
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

# An IP literal that is emphatically not loopback, for the pair that keeps the class
# honest. TEST-NET-3 (RFC 5737): reserved for documentation, routable nowhere, so
# the row says "an address, and not a loopback one" without naming anybody's host.
NON_LOOPBACK_IP_LITERAL = "203.0.113.10"

# The three spellings the **transport rule's exemption** is asserted over. A
# different question from the class above, and a separate constant on purpose: this
# is `app.config`'s existing `is_on_this_machine`, whose own pairs live in
# `tests/unit/test_ai_provider_configuration.py`, and this ticket widens the refusal
# rather than that exemption. Whether one helper ends up serving both is the
# implementation's call — nothing here asserts that a cleartext `127.0.0.2` *token*
# endpoint is accepted in a deployment, and nothing here asserts that it is refused.
ON_THIS_MACHINE_URL_HOSTS = ("localhost", "127.0.0.1", "[::1]")

# A second real provider, distinct from `DEPLOYED_HOST`, so a transport failure
# message reads as being about the row's own value rather than about one of the
# background values having moved.
ANOTHER_REAL_HOST = "sso.example.edu"

# The environments the review's rules are parametrised over. Fewer rows than
# `NON_DEVELOPMENT_ENVIRONMENTS` on purpose: *which* names count as a deployment is
# settled once, by `test_a_url_addressing_the_mock_is_refused_outside_development`,
# and repeating its four rows under every rule below would be four copies of one
# assertion rather than four assertions.
DEPLOYMENT_ENVIRONMENTS = ("production", "staging")


def load_settings_class() -> type:
    """Import `Settings` inside the test, so a missing module fails one test loudly.

    Spelled as `tests/unit/test_config_settings.py` and
    `tests/unit/test_ai_provider_configuration.py` spell it. An implementation that
    builds settings at import time raises at the import instead, which is still
    "raises at startup" — so every refusal below does the import inside the
    `pytest.raises` block.
    """
    from app.config import Settings

    return Settings


def load_configuration_error() -> type[BaseException]:
    """The error type the application promises its callers, imported inside the test.

    Named rather than caught as `Exception`, for the reason
    `test_ai_provider_configuration.py` gives on the same import: a bare `Exception`
    is satisfied by an `AttributeError` out of `load_settings_class()` if `Settings`
    is renamed or moved, which is a broken test reading as a refused configuration —
    the exact inversion this suite exists to prevent.
    """
    from app.config import ConfigurationError

    return ConfigurationError


def development_environment() -> str:
    """The `ENVIRONMENT` value that means development, read from its one definition.

    Out of `app.config` rather than written here, because E0-37 item 2 made that
    constant the single definition site and a literal in this module would be one
    more copy of the value that item exists to remove.
    """
    from app.config import DEVELOPMENT_ENVIRONMENT

    assert isinstance(DEVELOPMENT_ENVIRONMENT, str) and DEVELOPMENT_ENVIRONMENT, (
        "`app.config.DEVELOPMENT_ENVIRONMENT` is not a non-empty string, so this module cannot "
        "tell which environment the mock is permitted in. E0-37 item 2 makes it the one place "
        "that value is written down."
    )
    return DEVELOPMENT_ENVIRONMENT


def configure(monkeypatch: pytest.MonkeyPatch, values: Mapping[str, str | None]) -> None:
    """Set each variable, or remove it where the value is `None`.

    Removal is spelled as a value rather than as a second call so that a table of
    cases can say "this one is absent" in the same shape as "this one is wrong".
    """
    for name, value in values.items():
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)


def deployment(**overrides: str | None) -> dict[str, str | None]:
    """The five settings a real deployment holds, with `overrides` applied.

    Keyword names are the variables, so a caller writes
    `deployment(OIDC_ISSUER=...)`. Every test that asks about one bad value builds
    it this way rather than leaving the other four at `.env.example`'s
    placeholders, which are the mock's — otherwise a refusal that fired on a
    neighbouring value would read as the rule under test firing
    (`docs/MISTAKES.md` entry 3).
    """
    values: dict[str, str | None] = dict(DEPLOYED_OIDC)
    values.update(overrides)
    return values


def environment_named(template: str) -> str:
    """One row of `NON_DEVELOPMENT_ENVIRONMENTS`, with the development name filled in."""
    name = template.format(development=development_environment())
    assert name != development_environment(), (
        f"The environment row {template!r} resolves to the development environment itself, so "
        "the test using it would be asserting the development case under a non-development "
        "name. That row has to differ from `app.config.DEVELOPMENT_ENVIRONMENT`."
    )
    return name


# ---------------------------------------------------------------------------
# Layer 1 — the five settings are required, and the refusal names the field.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("missing", REQUIRED_OIDC_VARIABLES)
def test_an_absent_provider_setting_is_refused_in_development_naming_it(
    configured_env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    missing: str,
) -> None:
    """A process with no identity provider stops at startup, wherever it is running.

    E0-01 criterion 2 for the five settings ADR 0075 exempted from it: no silent
    fallback to a working default, and a message naming the variable so that an
    operator reading a container log knows what to set. ADR 0077 reverses that
    exemption because the default was not inert — `http://mock-idp:8000` is a
    service the base Compose file starts in every deployment, so the value a
    deployment "forgot" resolves, answers, and signs tokens for any identity asked
    for.

    Development is the environment here deliberately. It is the one place the
    forgotten value used to be harmless, so it is where "required" is most likely to
    be implemented as "required outside development" — which would leave every
    developer's laptop trusting the mock by omission and would make the pair below
    the only red.

    **The mutation this kills:** any of the five keeping a default, in any spelling
    — a literal, a `Field(default=...)`, or a validator that fills one in. **The
    near miss that must stay green:** the four values that are *present* are the
    mock's, since `configured_env` lays down `.env.example`'s placeholders, and
    development is where those are legal — so this must fail for the absent
    variable rather than for its neighbours.

    Matched case-insensitively: whether the message says `OIDC_ISSUER` or
    `oidc_issuer` is not something the ticket decides, and an operator greps for
    either.
    """
    configure(monkeypatch, {ENVIRONMENT_VARIABLE: development_environment(), missing: None})

    with pytest.raises(load_configuration_error(), match=f"(?i){missing}"):
        load_settings_class()()


@pytest.mark.parametrize("missing", REQUIRED_OIDC_VARIABLES)
def test_an_absent_provider_setting_is_refused_in_a_deployment_naming_it(
    configured_env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    missing: str,
) -> None:
    """The same requirement in a deployment, with nothing else wrong to hide behind.

    The pair to the test above, and it is not the same test twice. Every other
    setting here is a real provider's, so the only thing wrong with this
    configuration is the one absent variable — which is what makes the message
    assertion mean something. Run with `.env.example`'s placeholders instead, the
    refusal could just as well be layer 2 firing on `OIDC_ISSUER`'s mock host while
    naming a variable that happens to be the one this row removed.

    **The mutation this kills:** a requirement implemented only in development, and
    a refusal that names the first bad field it finds rather than the missing one.
    """
    configure(
        monkeypatch,
        {ENVIRONMENT_VARIABLE: "production", **deployment(**{missing: None})},
    )

    with pytest.raises(load_configuration_error(), match=f"(?i){missing}"):
        load_settings_class()()


# ---------------------------------------------------------------------------
# Layer 2 — a mock address is refused outside development, and only there.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("environment", NON_DEVELOPMENT_ENVIRONMENTS)
@pytest.mark.parametrize("variable", OIDC_URL_VARIABLES)
def test_a_url_addressing_the_mock_is_refused_outside_development(
    configured_env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    variable: str,
    environment: str,
) -> None:
    """Any one of the four URLs pointed at the mock stops a deployment at startup.

    All four, because they fail differently and a rule that covered some of them
    would read as covering the door. `oidc_jwks_url` and `oidc_token_endpoint` are
    fetched, so a mock there mints the session; `oidc_issuer` is never fetched at
    all — it is compared against the `iss` claim as a string (OIDC Core 1.0 §3.1.3.7)
    — so a mock there is what makes the mock's tokens *acceptable*; and
    `oidc_authorization_endpoint` is where a real browser is sent, so a mock there
    is the login page a person is asked to trust.

    Four environments, because the two obvious one-line conditions each pass some
    rows and fail others: `environment == "production"` lets staging trust the mock,
    and `DEVELOPMENT_ENVIRONMENT in environment` lets anything named after
    development trust it. A rule asserted on one row would be satisfied by either.

    **The mutation this kills:** no validator at all, which is the state at HEAD;
    and a validator that reads one field, or one environment name. **The near miss
    that must stay green:** the same values with `ENVIRONMENT` set to the
    development name, which is the test below.

    **The value carries TLS, so only the catalog can be what refuses it.** The
    development stack spells this address `http://mock-idp:8000`, and that spelling
    is a row in `MOCK_URL_SPELLINGS` below — but the security review added a
    transport rule that refuses cleartext off this machine outside development, so
    an `http` value here would be refused by either rule and this test could no
    longer say which (`docs/MISTAKES.md` entry 3). `https` isolates it.
    """
    configure(
        monkeypatch,
        {
            ENVIRONMENT_VARIABLE: environment_named(environment),
            **deployment(**{variable: f"https://{MOCK_SERVICE}:8443/oidc/token"}),
        },
    )

    with pytest.raises(load_configuration_error()):
        load_settings_class()()


@pytest.mark.parametrize("spelling", list(MOCK_URL_SPELLINGS))
def test_the_mock_host_is_refused_however_the_url_is_spelled(
    configured_env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    spelling: str,
) -> None:
    """The rule is about the host, so the port, the scheme and the path do not excuse it.

    A container on this network reaches the mock at `mock-idp` on whatever port it
    listens on, so a rule written against `http://mock-idp:8000` — the exact string
    `.env.example` ships, and the obvious thing to compare — is defeated by an
    operator who copies the address and changes the port, or who terminates TLS in
    front of it.

    **The mutation this kills:** equality against the development stack's full URL,
    or against `host:port` rather than the host.

    **Attribution, after the security review.** Four of these five rows are
    cleartext, and the transport rule added by that review refuses cleartext off
    this machine outside development as well — so those four are refused by either
    rule and cannot on their own say which one fired. That is accepted here rather
    than repaired, because the subject of this test is the *spelling of the address*
    and the cleartext spellings are the ones that actually ship. The row that
    isolates the catalog is "https on another port", and
    `test_the_mock_host_is_refused_with_a_trailing_dot` isolates it again on a
    different axis.
    """
    configure(
        monkeypatch,
        {
            ENVIRONMENT_VARIABLE: "production",
            **deployment(**{OIDC_TOKEN_ENDPOINT_VARIABLE: MOCK_URL_SPELLINGS[spelling]}),
        },
    )

    with pytest.raises(load_configuration_error()):
        load_settings_class()()


def test_the_mock_host_is_refused_whatever_case_it_is_written_in(
    configured_env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`MOCK-IDP` is the same host as `mock-idp`, so the refusal has to read it as one.

    Host names are case-insensitive (RFC 4343), and Compose resolves a service name
    without folding anything of its own — so `MOCK-IDP` in a container reaches the
    mock exactly as the lower-case spelling does. This is the one row in the module
    that is a judgement rather than a transcription of the ticket, and it is a narrow
    one: the ticket says the refusal is about the URL's *host*, and this is that
    host.

    **The mutation this kills:** `url.netloc.split(":")[0] == "mock-idp"`, which
    does not fold case, as against `urlsplit(url).hostname`, which does. Written as
    its own test rather than as a row above so that a dispute about the reading
    costs one test rather than five.

    `https`, so the transport rule the security review added cannot be what refuses
    this: the question is whether the catalog reads the host, and a cleartext value
    would be refused either way.
    """
    configure(
        monkeypatch,
        {
            ENVIRONMENT_VARIABLE: "production",
            **deployment(
                **{OIDC_TOKEN_ENDPOINT_VARIABLE: f"https://{MOCK_SERVICE.upper()}:8443/oidc/token"}
            ),
        },
    )

    with pytest.raises(load_configuration_error()):
        load_settings_class()()


@pytest.mark.parametrize("environment", NON_DEVELOPMENT_ENVIRONMENTS)
def test_the_mock_client_id_is_refused_outside_development(
    configured_env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    environment: str,
) -> None:
    """The second spelling: naming the mock's client, with every URL pointed elsewhere.

    This is the case a host rule cannot see. `oidc_client_id` is not a URL, so a
    validator phrased over "every `oidc_*` URL whose host is the mock" covers four
    of the five settings and reads as covering the surface — and the value it misses
    is the one that says *which registration* this tool is. A deployment carrying
    the mock's client id is a deployment configured to be the mock's client, which
    is the state ADR 0077 refuses even where the addresses have moved on.

    **The mutation this kills:** a validator that iterates the URL settings only.
    **The near miss that must stay green:** a client id that merely contains the
    mock's, two tests below.
    """
    configure(
        monkeypatch,
        {
            ENVIRONMENT_VARIABLE: environment_named(environment),
            **deployment(**{OIDC_CLIENT_ID_VARIABLE: MOCK_CLIENT_ID}),
        },
    )

    with pytest.raises(load_configuration_error()):
        load_settings_class()()


def test_the_refusal_of_a_mock_url_names_the_field_without_quoting_the_value(
    configured_env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """What the operator reads: which setting is wrong, and no more of it than the host.

    Both halves are the ticket's — "the refusal names the field, never echoes a
    value beyond the offending host" — and each is here because the other is
    satisfiable on its own. A refusal that says only "a mock address is configured"
    leaves an operator to find which of five settings carries it. A refusal that
    quotes the whole configured value back writes a deployment's configuration into
    the container startup log, which is the surface SPEC §10 keeps values out of and
    the text a person pastes into a chat window when asking for help.

    Nothing else about the wording is pinned. The host may appear — it is what is
    being refused — and the sentence around it should stay improvable.

    **The mutation this kills, corrected against a measurement.** This docstring
    first named "an f-string refusal built from the offending URL", and that
    mutation cannot leak. `_describe_invalid_settings` assembles what the operator
    reads out of the field name, the field's static description and pydantic's error
    code, and discards the validator's own message entirely — so a validator that
    quoted the URL back would be green here against every implementation, and the
    test would have been asserting a property nothing could violate.

    What this actually guards is the **assembly**. Putting `detail.get("input")`
    into the line that function builds writes the configured value into the
    container startup log, for every refused setting at once, which is the surface
    SPEC §10 keeps values out of. E0-39's verifier ran exactly that mutation as part
    of the battery and exactly this test went red for it.

    The measurement is the verifier's rather than this module's — a test author does
    not read `app/config.py` — so the account above names the function rather than a
    line number, which would go stale on the next edit to that file.
    """
    # `https`, so the transport rule cannot be what refuses this: the assertions
    # below are about what a *catalog* refusal says, and the two rules write their
    # messages through the same assembly.
    offending = f"https://{MOCK_SERVICE}:8443/oidc/token?tenant=e0-39"
    configure(
        monkeypatch,
        {
            ENVIRONMENT_VARIABLE: "production",
            **deployment(**{OIDC_TOKEN_ENDPOINT_VARIABLE: offending}),
        },
    )

    with pytest.raises(load_configuration_error()) as refusal:
        load_settings_class()()

    message = str(refusal.value)
    assert OIDC_TOKEN_ENDPOINT_VARIABLE.lower() in message.lower(), (
        f"The refusal does not name {OIDC_TOKEN_ENDPOINT_VARIABLE}: {message!r}. Five settings "
        "can carry a mock address and the operator reading a container log has to learn which "
        "one did."
    )
    assert offending not in message, (
        f"The refusal quotes the configured value back in full: {message!r}. The host is what is "
        "being refused and may be named; the rest of the value is this deployment's "
        "configuration, and a startup error goes to the log stream and into whatever gets pasted "
        "when somebody asks for help (SPEC §10)."
    )


def test_the_refusal_of_the_mock_client_id_names_the_field(
    configured_env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The same, for the setting that is not a URL.

    Its own test because the two refusals are two code paths — one reads a parsed
    host, the other compares a whole string — and a message written on one of them
    says nothing about the other.

    **The mutation this kills:** a client-id refusal that raises the right type with
    a message about the URLs, which sends an operator to look at four settings that
    are correct.
    """
    configure(
        monkeypatch,
        {
            ENVIRONMENT_VARIABLE: "production",
            **deployment(**{OIDC_CLIENT_ID_VARIABLE: MOCK_CLIENT_ID}),
        },
    )

    with pytest.raises(load_configuration_error()) as refusal:
        load_settings_class()()

    message = str(refusal.value)
    assert OIDC_CLIENT_ID_VARIABLE.lower() in message.lower(), (
        f"The refusal does not name {OIDC_CLIENT_ID_VARIABLE}: {message!r}. It is the setting "
        "that is wrong, and it is not one of the four URLs a message about addresses would send "
        "the operator to."
    )


# ---------------------------------------------------------------------------
# The other direction. Without these, a validator that refuses everything outside
# development — or one that refuses the development stack too — is green above and
# has closed the web door.
# ---------------------------------------------------------------------------


def test_the_development_stack_configuration_is_accepted_in_development(
    configured_env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`docker compose up` from a clean checkout still reaches a system a person can log in to.

    SPEC §14.3 is the criterion and this is the pair that protects it. The values
    are `.env.example`'s own, laid down by `configured_env`, which is what CI copies
    to `.env` — three of the four URLs address `mock-idp` and the client id is
    `mock-idp-client`, and in development every one of them is correct.

    **The mutation this kills:** a refusal that does not read `ENVIRONMENT` at all,
    which is the natural first draft of the validator and which passes every
    refusal test above. A red here after the ticket lands means the development
    stack no longer starts.

    **A red here today means these tests are broken, not the code**: nothing is
    implemented yet, so this is asserting that the fixture machinery builds a
    `Settings` that passes.
    """
    configure(monkeypatch, {ENVIRONMENT_VARIABLE: development_environment()})

    settings = load_settings_class()()

    assert settings is not None, (
        "`Settings()` answered nothing for the configuration `.env.example` documents and CI "
        "copies to `.env`. Everything in E0's exit criterion runs from this file."
    )


@pytest.mark.parametrize("environment", NON_DEVELOPMENT_ENVIRONMENTS)
def test_a_deployment_naming_no_mock_is_accepted(
    configured_env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    environment: str,
) -> None:
    """The point of the whole ticket: a real provider configured in a real deployment works.

    Every refusal above is satisfied by a validator that raises whenever
    `ENVIRONMENT` is not the development name, which would make the web door
    undeployable. This is the row that says the rule is about the mock rather than
    about deployments.

    **A red here today means these tests are broken, not the code.** No validator
    exists yet, so what this asserts today is that `DEPLOYED_OIDC` is a
    configuration `Settings` accepts — the control every refusal above is measured
    against.
    """
    configure(monkeypatch, {ENVIRONMENT_VARIABLE: environment_named(environment), **deployment()})

    settings = load_settings_class()()

    assert settings is not None, (
        f"`Settings()` refused a configuration naming no mock, with {ENVIRONMENT_VARIABLE} set "
        f"to {environment_named(environment)!r}. The rule is about the mock's two spellings; a "
        "rule that refuses a deployment outright leaves SPEC §2's web login door unreachable "
        "anywhere it is meant to be used."
    )


@pytest.mark.parametrize("spelling", list(NON_MOCK_URL_SPELLINGS))
def test_a_url_that_merely_contains_the_service_name_is_accepted(
    configured_env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    spelling: str,
) -> None:
    """The host is compared as a component, not searched for as a substring.

    Each row is an address a real institution could hold, and each is refused by the
    one-line version of this rule — `"mock-idp" in url` — that is the obvious way to
    write it and that the tests above cannot tell from the right one. A subdomain,
    a host the name prefixes, a host the name ends, and a path segment: none of them
    resolves to the Compose service, which is the only thing the catalog names.

    **The mutation this kills:** substring matching, over the URL or over the host.
    **The near miss on the other side:** `MOCK_URL_SPELLINGS` above, where the host
    is exactly the service name and every one is refused.
    """
    configure(
        monkeypatch,
        {
            ENVIRONMENT_VARIABLE: "production",
            **deployment(**{OIDC_TOKEN_ENDPOINT_VARIABLE: NON_MOCK_URL_SPELLINGS[spelling]}),
        },
    )

    settings = load_settings_class()()

    assert settings is not None, (
        f"`Settings()` refused {NON_MOCK_URL_SPELLINGS[spelling]!r}, whose host is "
        f"{urlsplit(NON_MOCK_URL_SPELLINGS[spelling]).hostname!r} and not {MOCK_SERVICE!r}. The "
        "catalog is the Compose service name — the name by which a container on this stack "
        "reaches the mock — and nothing else resolves to it."
    )


@pytest.mark.parametrize("spelling", list(NON_MOCK_CLIENT_IDS))
def test_a_client_id_that_merely_contains_the_mocks_is_accepted(
    configured_env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    spelling: str,
) -> None:
    """The client id is compared whole, for the same reason the host is.

    A registration named `mock-idp-client-2` at a real provider is a real client id,
    and an institution that named its own registration after the tool it replaced is
    not this rule's business. The catalog is one value.

    **The mutation this kills:** `MOCK_CLIENT_ID in settings.oidc_client_id`.
    """
    configure(
        monkeypatch,
        {
            ENVIRONMENT_VARIABLE: "production",
            **deployment(**{OIDC_CLIENT_ID_VARIABLE: NON_MOCK_CLIENT_IDS[spelling]}),
        },
    )

    settings = load_settings_class()()

    assert settings is not None, (
        f"`Settings()` refused the client id {NON_MOCK_CLIENT_IDS[spelling]!r}, which is not "
        f"{MOCK_CLIENT_ID!r}. The catalog is the mock's registered client id, compared as a "
        "whole value."
    )


def test_a_localhost_provider_is_not_read_as_the_mock_in_a_deployment(
    configured_env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`localhost` is deliberately outside the **mock** catalog, and this is what says so.

    ADR 0077 has to justify the exclusion; this asserts it, so that a later widening
    is a red test and a reviewed decision rather than a quiet tightening. The
    reasoning is that inside a deployed container `localhost` cannot resolve to the
    mock — it is that container itself — so treating it as the mock would refuse a
    provider running beside the application, which is a supported deployment, while
    protecting nothing.

    **Narrowed by the security review, and the narrowing is the point.** This test
    used to set the browser-facing endpoint to `http://localhost:8081/oidc/authorize`
    in production and require it accepted, which is the MEDIUM the review found: that
    value is not resolved in the container at all, it is handed to a browser and
    resolved on the end user's machine. The finding does not touch this test's
    subject — `localhost` still is not the mock — so what changed is the field it
    asks about, from a browser-facing one to the two that the container fetches.
    `test_a_loopback_authorization_endpoint_is_refused_outside_development` now owns
    the other field, and asserts the opposite of what this test used to.

    **The mutation this kills:** `localhost` or `127.0.0.1` added to the mock
    catalog. **The near miss that must stay red:** the same host on
    `oidc_authorization_endpoint`, which is refused — by a different rule, for a
    different reason.
    """
    configure(
        monkeypatch,
        {
            ENVIRONMENT_VARIABLE: "production",
            **deployment(
                **{
                    OIDC_TOKEN_ENDPOINT_VARIABLE: "https://localhost:8443/oidc/token",
                    OIDC_JWKS_URL_VARIABLE: "https://127.0.0.1:8443/.well-known/jwks.json",
                }
            ),
        },
    )

    settings = load_settings_class()()

    assert settings is not None, (
        "`Settings()` refused a provider on this machine as though it were the mock. Inside a "
        "deployed container `localhost` is that container, so it cannot reach the mock, and "
        "reading it as the mock refuses a provider running alongside the application (ADR 0077)."
    )


# ---------------------------------------------------------------------------
# Controls on the catalog. Two strings decide everything above, and a stale one
# refuses nothing while reporting exactly what a correct one reports
# (`docs/MISTAKES.md` entry 35).
# ---------------------------------------------------------------------------


def test_the_refused_host_is_the_compose_service_name_the_mock_actually_runs_as(
    mock_idp_service: str,
) -> None:
    """A control: the host this module refuses is the name SPEC §7.2 gives the service.

    **A red here means these tests are broken, or the mock has been renamed.** The
    catalog is written out above rather than derived, which is the right call for a
    two-entry rule that a reviewed diff should have to change — but a written-out
    catalog can go stale without anything failing, since a rule that refuses a name
    nothing runs under reports every configuration clean.

    `mock_idp_service` is `tests/fixtures/mock_idp.py`'s single answer to "what is the mock
    called", used by every other module that reasons about it.
    """
    assert mock_idp_service == MOCK_SERVICE, (
        f"This module refuses the host {MOCK_SERVICE!r} and the mock provider runs as the Compose "
        f"service {mock_idp_service!r}. Every refusal above is then about a name nothing on this "
        "stack answers to, and would pass against a deployment configured with the real one."
    )


def test_the_refused_client_id_is_the_one_the_development_stack_configures(
    documented_env: dict[str, str],
) -> None:
    """A control: the client id this module refuses is the one `.env.example` ships.

    **A red here means these tests are broken, or the mock's registration has been
    renamed.** The same staleness as above, on the spelling that has no service name
    behind it to compare with: the mock's registered client is a value in the mock's
    own configuration, and the evidence available here that this repository uses it
    is that the development stack is configured with it.

    Asserted against `.env.example` rather than against `mock-idp/app/`, because
    what layer 2 refuses is a *configuration* — the value an operator would carry
    forward from the development stack into a deployment — and that is exactly what
    this file holds.
    """
    assert documented_env, (
        ".env.example is missing or parsed to nothing, so this control has nothing to compare "
        "the catalog against and would report it fresh whatever it says."
    )
    configured = documented_env.get(OIDC_CLIENT_ID_VARIABLE)
    assert configured == MOCK_CLIENT_ID, (
        f"This module refuses the client id {MOCK_CLIENT_ID!r} and `.env.example` configures "
        f"{configured!r}. The refusal is aimed at the value an operator copies out of the "
        "development stack, so the two have to be the same string — and if the mock's "
        "registration has been renamed, this constant is the line that changes."
    )


def test_the_deployed_sample_configuration_names_no_mock_anywhere() -> None:
    """A control: the values every acceptance and every isolated refusal is built on.

    **A red here means these tests are broken, not the code.** `deployment()` is the
    background of most of the module: a refusal test sets four settings from it and
    one bad value, and an acceptance test sets all five. If any of those five
    carried the mock's name, every refusal row above would pass whatever value it
    set — the rule would be firing on the background rather than on the subject —
    and every acceptance row would be asserting that the mock is accepted in
    production, which is the opposite of the ticket.

    Nothing here imports the application; it is arithmetic on this module's own
    constants, which is why it can be relied on to say something about the rest.
    """
    for variable, value in DEPLOYED_OIDC.items():
        assert MOCK_SERVICE not in value, (
            f"The deployed sample value for {variable} is {value!r}, which contains "
            f"{MOCK_SERVICE!r}. Every test built on `deployment()` then has the mock in its "
            "background, and a refusal that fired on this value would read as the rule under "
            "test firing."
        )
    assert DEPLOYED_OIDC[OIDC_CLIENT_ID_VARIABLE] != MOCK_CLIENT_ID, (
        "The deployed sample client id is the mock's, so every test that leaves the client id "
        "alone is configured as the mock's client."
    )


# ---------------------------------------------------------------------------
# The security review's findings. Everything above refuses the mock by name; each
# rule here refuses a configuration that reaches the same outcome without ever
# spelling `mock-idp` — which is the shape a catalog rule invites, and the reason
# the review looked for them.
#
# Every refusal below is written so that exactly one rule can be what fires. The
# loopback rows carry `https`, so the transport rule cannot be the refusal; the
# trailing-dot row carries `https` for the same reason. Where two rules genuinely
# overlap there is a test that says so by name, rather than a row whose green
# nobody can attribute (`docs/MISTAKES.md` entry 3).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("environment", DEPLOYMENT_ENVIRONMENTS)
@pytest.mark.parametrize("spelling", list(LOOPBACK_URL_HOSTS))
def test_a_loopback_authorization_endpoint_is_refused_outside_development(
    configured_env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    spelling: str,
    environment: str,
) -> None:
    """The browser-facing endpoint may not point at the end user's own machine.

    **The finding.** `OIDC_AUTHORIZATION_ENDPOINT`'s development value is
    `http://localhost:8081/oidc/authorize`, and `localhost` is not the mock's name,
    so a deployment that sets the other four and misses this one starts perfectly
    cleanly — and then answers every web login with a 302 to a port on the browsing
    user's own computer. Anything listening there receives an institution-issued
    link that arrived at a Pulse URL, and renders whatever it likes: a login page,
    asking for the credentials the real provider would have asked for.

    **Why this field and not the other four.** The four server-side settings are
    resolved by the container: `localhost` there is the container itself, which is
    a supported deployment (a provider sidecar) and reaches nothing an attacker
    controls. This one is never resolved in the container at all — it is a string
    handed to a browser, resolved on the machine that browser is running on. So the
    same host name means "this API process" in four settings and "whoever's laptop
    is reading this" in the fifth, and only the fifth is a finding.

    **Five spellings, because the rule is a class rather than a list.** `[::1]` is
    what a machine with IPv6 resolves `localhost` to first; `127.0.0.2` is an
    ordinary address in `127.0.0.0/8`, every one of which is the local machine; and
    `::ffff:127.0.0.1` is the IPv4-mapped form, which reads as loopback on this
    interpreter and is invisible to any comparison against a spelling. The
    reviewer's finding arrived with a fourth spelling already in it, so a catalog was
    never going to be the answer — the constant above records why.

    **The one-level-out mutation this kills, which is the point of the extra rows:**
    a rule reverted to the three literal spellings `localhost`, `127.0.0.1` and
    `[::1]`. That passes the first, second and fourth rows here and must go red on
    `127.0.0.2` and on `[::ffff:127.0.0.1]`. Anything narrower than "the host is
    `localhost`, or `ipaddress` says this literal is loopback" fails one of those
    two.

    **https, deliberately.** The transport rule below also refuses cleartext off
    this machine; carrying TLS here means the only thing wrong with this URL is its
    host, so a green row cannot be the other rule firing.

    **The other mutations this kills:** the loopback rule dropped, applied to all
    five settings, or applied to none. **The near misses that must stay green:** the
    same URLs in development, which is the pair below; a loopback *token* endpoint
    outside development, which is a sidecar; and a non-loopback IP literal on this
    same field, which is an institution that runs its provider at an address.
    """
    configure(
        monkeypatch,
        {
            ENVIRONMENT_VARIABLE: environment,
            **deployment(
                **{
                    OIDC_AUTHORIZATION_ENDPOINT_VARIABLE: (
                        f"https://{LOOPBACK_URL_HOSTS[spelling]}:8081/oidc/authorize"
                    )
                }
            ),
        },
    )

    with pytest.raises(load_configuration_error()):
        load_settings_class()()


@pytest.mark.parametrize("scheme", ("http", "https"))
@pytest.mark.parametrize("spelling", list(LOOPBACK_URL_HOSTS))
def test_a_loopback_authorization_endpoint_is_accepted_in_development(
    configured_env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    spelling: str,
    scheme: str,
) -> None:
    """The exact pair: the same URLs, one environment different.

    `http://localhost:8081/oidc/authorize` is what `.env.example` ships and what the
    override publishes the mock on, because a browser on the developer's host
    reaches it there. The rule above must not touch it, and this is the row that
    says so — a loopback refusal written without the environment condition closes
    the web door on every laptop and passes every refusal test in this module.

    The same five spellings, so that widening the rule into a class cannot narrow
    what development accepts: `127.0.0.2:8081` is refused in a deployment by the row
    above and has to be accepted here, and a developer who runs the mock on a second
    loopback address is doing nothing wrong.

    Both schemes, since the development stack uses cleartext and the rule above is
    written over TLS; neither may be refused here.

    **The mutation this kills:** the loopback rule applied unconditionally — in
    particular a class-based rule that forgot the environment condition the three
    literal spellings had.
    """
    host = LOOPBACK_URL_HOSTS[spelling]
    configure(
        monkeypatch,
        {
            ENVIRONMENT_VARIABLE: development_environment(),
            **deployment(
                **{OIDC_AUTHORIZATION_ENDPOINT_VARIABLE: (f"{scheme}://{host}:8081/oidc/authorize")}
            ),
        },
    )

    settings = load_settings_class()()

    assert settings is not None, (
        f"`Settings()` refused {scheme}://{host}:8081/oidc/authorize in development. The first of "
        "these is the address `.env.example` ships and the one a browser on the developer's host "
        "reaches the mock at, so refusing it closes the web login door on every laptop."
    )


def test_a_non_loopback_ip_literal_authorization_endpoint_is_accepted_outside_development(
    configured_env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The pair that keeps the class honest: an address is not the same as loopback.

    The refusal above closes over a class rather than a list, and the cheapest way to
    satisfy a class-based rule is to widen it past the class — "the host is an IP
    literal" instead of "the host is an IP literal that is loopback". An institution
    that runs its identity provider at an address rather than a name is then
    undeployable, and every refusal row above stays green.

    TEST-NET-3 (RFC 5737), so the row is unambiguously an address and unambiguously
    not loopback, and names nobody's real host.

    **The mutation this kills:** `ipaddress.ip_address(host)` succeeding treated as
    the refusal, rather than `.is_loopback` on the parsed result. **Its pair** is the
    `127.0.0.2` row above, which the same broken rule also passes — the two together
    are what require the loopback test rather than the parse.
    """
    configure(
        monkeypatch,
        {
            ENVIRONMENT_VARIABLE: "production",
            **deployment(
                **{
                    OIDC_AUTHORIZATION_ENDPOINT_VARIABLE: (
                        f"https://{NON_LOOPBACK_IP_LITERAL}/oidc/authorize"
                    )
                }
            ),
        },
    )

    settings = load_settings_class()()

    assert settings is not None, (
        f"`Settings()` refused https://{NON_LOOPBACK_IP_LITERAL}/oidc/authorize in production. "
        "That is a documentation address, routable nowhere near this process, and the rule is "
        "about loopback rather than about IP literals: a provider reached at an address instead "
        "of a name is an ordinary deployment."
    )


def test_a_real_authorization_endpoint_is_accepted_outside_development(
    configured_env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The other pair: a browser-facing endpoint at a real provider still deploys.

    Without this, the rule above is satisfied by refusing every authorization
    endpoint outside development, which is the web door closed in exactly the
    deployments it exists for. A second real host rather than
    `DEPLOYED_OIDC`'s own, so this row says something the whole-set acceptance test
    does not: that the field is judged on its host rather than on being left at the
    value this module happens to use as a background.
    """
    configure(
        monkeypatch,
        {
            ENVIRONMENT_VARIABLE: "production",
            **deployment(
                **{
                    OIDC_AUTHORIZATION_ENDPOINT_VARIABLE: (
                        f"https://{ANOTHER_REAL_HOST}/oidc/authorize"
                    )
                }
            ),
        },
    )

    settings = load_settings_class()()

    assert settings is not None, (
        f"`Settings()` refused https://{ANOTHER_REAL_HOST}/oidc/authorize in production. It is "
        "neither the mock nor this machine, which is what an institution's own provider looks "
        "like — and a rule that refuses it leaves the web door undeployable."
    )


def test_a_loopback_token_endpoint_is_accepted_outside_development(
    configured_env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The composition, stated from the side where the two rules do not agree.

    The loopback refusal is about one field, and this is what says so. A provider
    running beside the application — a sidecar in the same pod, or on the same host
    — is reached by the container at `localhost`, and the four server-side settings
    may point there in any environment. Sweeping loopback out of all five would
    refuse that deployment while protecting nothing, because none of those four is
    ever handed to a browser.

    **The mutation this kills:** the loopback catalog applied to every `oidc_*` URL
    rather than to the browser-facing one. **Its pair** is the first test in this
    section, where the identical host under the identical environment is refused
    because the field is the one a browser reads.
    """
    configure(
        monkeypatch,
        {
            ENVIRONMENT_VARIABLE: "production",
            **deployment(
                **{
                    OIDC_TOKEN_ENDPOINT_VARIABLE: "https://localhost:8443/oidc/token",
                    OIDC_JWKS_URL_VARIABLE: "https://localhost:8443/.well-known/jwks.json",
                }
            ),
        },
    )

    settings = load_settings_class()()

    assert settings is not None, (
        "`Settings()` refused a token endpoint and key set on this machine in production. Those "
        "two are fetched by the container, where `localhost` is the container itself — a provider "
        "sidecar, which is a deployment rather than a defect. The browser-facing endpoint is the "
        "one the loopback rule is about."
    )


def test_a_cleartext_loopback_authorization_endpoint_is_refused_outside_development(
    configured_env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Where the two rules overlap, the exemption must not be the one that wins.

    `http://localhost:8081/oidc/authorize` in a deployment is the finding's own
    value. The transport rule *exempts* cleartext to this machine; the loopback rule
    *refuses* this field pointed at this machine. Written as an early return — "on
    this machine, nothing more to check" — the exemption answers first and the
    finding is still open, with every other row in this section green.

    So this row is not a duplicate of the first test with a different scheme. It is
    the one that says the rules compose rather than short-circuit, and it is the
    exact configuration the review found.

    **The mutation this kills:** an on-this-machine check that returns early instead
    of continuing to the field-specific rule.
    """
    configure(
        monkeypatch,
        {
            ENVIRONMENT_VARIABLE: "production",
            **deployment(
                **{OIDC_AUTHORIZATION_ENDPOINT_VARIABLE: "http://localhost:8081/oidc/authorize"}
            ),
        },
    )

    with pytest.raises(load_configuration_error()):
        load_settings_class()()


@pytest.mark.parametrize("environment", DEPLOYMENT_ENVIRONMENTS)
@pytest.mark.parametrize("variable", OIDC_URL_VARIABLES)
def test_a_cleartext_endpoint_off_this_machine_is_refused_outside_development(
    configured_env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    variable: str,
    environment: str,
) -> None:
    """Cleartext to another host is refused, which is the same rule `app.config`
    already applies to the model provider.

    **The finding.** With no transport rule, `http://idp.example.edu/...` is a legal
    production configuration. Anyone on the path between the container and that host
    can answer the key-set fetch with a key set of their own, and every token signed
    with the matching private key then verifies — which is the signing oracle this
    whole ticket exists to close, reached without ever naming the mock.

    All four settings. The key set and the token endpoint are fetched, so the
    argument is direct. The authorization endpoint is a URL a browser is sent to, and
    cleartext there puts the authorization request and its `state` on the wire. The
    issuer is fetched by nothing at all — it is compared against the `iss` claim as a
    string — and it is included because OpenID Connect Discovery requires an Issuer
    Identifier to use the `https` scheme, so an `http` issuer is not a provider
    identity that any conformant deployment has.

    `app.config` already holds exactly this rule for `ai_provider_base_url`;
    `tests/unit/test_ai_provider_configuration.py` is where its pairs live, and the
    on-this-machine exemption below is that rule's, spelled the same way.

    **The mutation this kills:** no transport rule; a transport rule on the fetched
    endpoints only. **The near misses that must stay green:** cleartext in
    development, which is the whole development stack, and cleartext to this
    machine, which is a sidecar.
    """
    configure(
        monkeypatch,
        {
            ENVIRONMENT_VARIABLE: environment,
            **deployment(**{variable: f"http://{ANOTHER_REAL_HOST}/oidc/endpoint"}),
        },
    )

    with pytest.raises(load_configuration_error()):
        load_settings_class()()


@pytest.mark.parametrize(
    "variable",
    (OIDC_ISSUER_VARIABLE, OIDC_TOKEN_ENDPOINT_VARIABLE, OIDC_JWKS_URL_VARIABLE),
)
def test_a_cleartext_server_side_endpoint_on_this_machine_is_accepted_outside_development(
    configured_env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    variable: str,
) -> None:
    """The transport rule's exemption: there is no network between a process and itself.

    A provider running beside the application is reached over the loopback interface,
    where nothing can be read off the wire, and refusing it would turn away a
    deployment while protecting nothing — the same reasoning, in the same words, that
    `tests/unit/test_ai_provider_configuration.py` records for a local model server.

    The browser-facing endpoint is deliberately not a row here: for that field this
    same URL is *refused*, by the rule above it, and the test that says so by name is
    `test_a_cleartext_loopback_authorization_endpoint_is_refused_outside_development`.

    **The mutation this kills:** a transport rule written as "outside development,
    https or nothing".
    """
    configure(
        monkeypatch,
        {
            ENVIRONMENT_VARIABLE: "production",
            **deployment(**{variable: "http://localhost:8443/oidc/endpoint"}),
        },
    )

    settings = load_settings_class()()

    assert settings is not None, (
        f"`Settings()` refused a cleartext {variable} on this machine in production. There is no "
        "network between the process and a provider on the same machine, so there is nothing for "
        "a transport rule to protect — and `app.config` already makes this exemption for the "
        "model provider."
    )


@pytest.mark.parametrize("host", ON_THIS_MACHINE_URL_HOSTS)
def test_the_transport_exemption_covers_every_spelling_of_this_machine(
    configured_env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    host: str,
) -> None:
    """Three spellings of one permission, on the field that is fetched most often.

    The pair to the exemption above, asked the other way round: that one varies the
    field and holds the host, this one holds the field and varies the host. A rule
    written against `localhost` alone refuses the address, and one written against
    the address alone refuses the name; `[::1]` is what a machine with IPv6 resolves
    the name to first, so it is the spelling a rule is likeliest to miss.

    **The mutation this kills:** an on-this-machine check that knows one or two of
    the three spellings.
    """
    configure(
        monkeypatch,
        {
            ENVIRONMENT_VARIABLE: "production",
            **deployment(**{OIDC_JWKS_URL_VARIABLE: f"http://{host}:8443/jwks.json"}),
        },
    )

    settings = load_settings_class()()

    assert settings is not None, (
        f"`Settings()` refused http://{host}:8443/jwks.json in production, which is this machine "
        "written a third way. All three spellings are one permission."
    )


def test_the_development_stack_is_reached_over_cleartext_and_that_stays_legal(
    configured_env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The transport rule is conditioned on the environment, and this is why.

    Every address on the development stack is cleartext to a host that is *not* this
    machine: `http://mock-idp:8000` is another container. So the model provider's
    version of this rule — which is absolute, because a model provider has no
    equivalent of a development stack — would refuse the configuration
    `.env.example` ships and CI copies to `.env`, and E0's §14.3 exit criterion with
    it.

    **The mutation this kills:** the transport rule written without its environment
    condition, copied across from `ai_provider_base_url` where it does not need one.
    """
    configure(
        monkeypatch,
        {
            ENVIRONMENT_VARIABLE: development_environment(),
            OIDC_ISSUER_VARIABLE: f"http://{MOCK_SERVICE}:8000",
            OIDC_AUTHORIZATION_ENDPOINT_VARIABLE: "http://localhost:8081/oidc/authorize",
            OIDC_TOKEN_ENDPOINT_VARIABLE: f"http://{MOCK_SERVICE}:8000/oidc/token",
            OIDC_JWKS_URL_VARIABLE: f"http://{MOCK_SERVICE}:8000/.well-known/jwks.json",
            OIDC_CLIENT_ID_VARIABLE: MOCK_CLIENT_ID,
        },
    )

    settings = load_settings_class()()

    assert settings is not None, (
        "`Settings()` refused the development stack's own configuration, written out here rather "
        "than taken from `.env.example` so that this row keeps saying what it says if that file "
        "changes. Every address on it is cleartext to another container, so a transport rule "
        "without an environment condition takes the whole stack down."
    )


def test_the_mock_host_is_refused_with_a_trailing_dot(
    configured_env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`mock-idp.` and `mock-idp` are the same host to every resolver.

    A trailing dot makes a name fully qualified and is otherwise inert: a container
    given `https://mock-idp.:8443/oidc/token` reaches the mock exactly as it would
    without it. The catalog compares strings, so the dot walks straight through — and
    it is a one-character edit to a value copied out of the development stack.

    **https, so the transport rule cannot be what refuses it**, which is what makes
    a green here attributable to the catalog and nothing else.

    **The mutation this kills:** the catalog compared against `urlsplit(...).hostname`
    with no normalisation. **The near miss that must stay green:** the test below —
    a trailing dot on a host that is not the mock, which must not become refused by
    a normaliser that strips more than the dot.
    """
    configure(
        monkeypatch,
        {
            ENVIRONMENT_VARIABLE: "production",
            **deployment(**{OIDC_TOKEN_ENDPOINT_VARIABLE: f"https://{MOCK_SERVICE}.:8443/token"}),
        },
    )

    with pytest.raises(load_configuration_error()):
        load_settings_class()()


def test_a_loopback_authorization_endpoint_with_a_trailing_dot_is_refused(
    configured_env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The same normalisation, on the other catalog.

    `localhost.` resolves to the loopback interface exactly as `localhost` does, so
    a browser sent there is sent to the user's own machine — the first finding in
    this section, reached by the third one's route. Two catalogs and one
    normalisation: a fix that strips the dot before the mock comparison and not
    before the loopback comparison closes half of this.

    **The mutation this kills:** trailing-dot stripping applied at one comparison
    site rather than to the parsed host once, before every comparison.
    """
    configure(
        monkeypatch,
        {
            ENVIRONMENT_VARIABLE: "production",
            **deployment(
                **{OIDC_AUTHORIZATION_ENDPOINT_VARIABLE: "https://localhost.:8081/authorize"}
            ),
        },
    )

    with pytest.raises(load_configuration_error()):
        load_settings_class()()


def test_a_trailing_dot_on_a_host_that_is_not_the_mock_is_accepted(
    configured_env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The pair: normalising the dot must not widen what the catalog matches.

    `mock-idp.example.edu.` is a fully qualified name for a host that is not the
    Compose service, and it stays accepted — which is the same exact-host reading the
    module already pins, asked again after a normaliser has touched the value.

    **The mutation this kills:** a comparison that goes back to `startswith`, or to
    any prefix test, once the value is normalised. `mock-idp.example.edu` begins with
    `mock-idp`, so a rule that stopped comparing whole hosts refuses a real
    institutional address, and this row is what turns that red.

    **What it does not kill, named rather than implied.** This docstring used to
    claim a second mutation — a normaliser that strips *more* than one trailing dot —
    and the implementer measured that false: `rstrip(".")` leaves
    `mock-idp.example.edu.` as `mock-idp.example.edu`, which is still not
    `mock-idp`, so the row stays green and the claim was one nothing could violate
    (`docs/MISTAKES.md` entry 3). It is left unkilled deliberately rather than
    covered by a new row, because the whole cost of a multi-dot strip is that
    `mock-idp..` would be read as the mock and refused — and `mock-idp..` resolves
    nowhere, so that refusal protects nothing and costs nothing. The implementation
    records the same limit at `url_host`; if it ever becomes worth guarding, the
    row is `mock-idp..` and it belongs beside the refusals above rather than here.
    """
    configure(
        monkeypatch,
        {
            ENVIRONMENT_VARIABLE: "production",
            **deployment(
                **{OIDC_TOKEN_ENDPOINT_VARIABLE: f"https://{MOCK_SERVICE}.example.edu./token"}
            ),
        },
    )

    settings = load_settings_class()()

    assert settings is not None, (
        f"`Settings()` refused https://{MOCK_SERVICE}.example.edu./token, whose host is a fully "
        f"qualified name ending in `.example.edu.` and is not the Compose service {MOCK_SERVICE!r}. "
        "Stripping a trailing dot is normalisation; matching more hosts because of it is a wider "
        "catalog."
    )
