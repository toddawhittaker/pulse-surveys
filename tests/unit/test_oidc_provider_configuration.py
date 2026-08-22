"""The identity provider is configured per deployment, and the mock is refused outside it.

Ticket E0-39, and the epic-boundary threat model that raised it. `app.config`
defaulted `OIDC_ISSUER` to `http://mock-idp:8000`, the token endpoint and the key
set to addresses on the same service, and `OIDC_CLIENT_ID` to `mock-idp-client`,
while the base Compose file starts `mock-idp` in every deployment. An operator who
deploys per SPEC §7.2 and sets none of those variables has deployed a signing
oracle for fake CARE and ADMIN identities, which this tool then verifies correctly
and trusts. ADR 0075 chose those defaults deliberately; ADR 0077 reverses that half
of them.

Two layers, and the tests below are two matching halves of it.

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
in the set — inside a deployed container it cannot resolve to the mock — and that
is ADR 0077's to justify, not this module's to widen.

**The host component, compared exactly.** The ticket says "any `oidc_*` URL whose
host is `mock-idp`", and this module pins what "is" means: the URL's parsed host,
equal to the service name, rather than the service name appearing anywhere in the
URL. A substring rule would refuse `https://mock-idp.example.edu/oidc/token` — a
perfectly ordinary institutional address for a real provider — and would also fire
on a *path* segment, which addresses nothing. Both directions are asserted, in
pairs, so neither reading can be satisfied by accident.

**Every refusal is paired with an acceptance.** A validator that refuses
everything outside development, or that refuses the development stack too, passes
every refusal test here and closes both doors; the pairs are what stop that. The
sharpest of them is
`test_the_development_stack_configuration_is_accepted_in_development` — the whole
of E0's §14.3 exit criterion is that `docker compose up` from a clean checkout
reaches a system a person can log in to.

**Which failure a red here is.** Three tests are marked as controls in their
docstrings: they must be green today, before any of this is implemented, and a red
one means the machinery below is broken rather than that the configuration is.
Everything else in the first two sections is expected red until the ticket lands,
on an assertion or on `DID NOT RAISE` — never on an import, since `Settings` and
`ConfigurationError` both exist already.
"""

from collections.abc import Mapping
from urllib.parse import urlsplit

import pytest

# The variable each setting arrives in. **These spellings are not this module's
# choice** — `tests/conftest.py` already fixes them for E0-18's door suites, and
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
    """
    configure(
        monkeypatch,
        {
            ENVIRONMENT_VARIABLE: environment_named(environment),
            **deployment(**{variable: f"http://{MOCK_SERVICE}:8000/oidc/token"}),
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
    without folding anything of its own — so `http://MOCK-IDP:8000/oidc/token` in a
    container reaches the mock exactly as the lower-case spelling does. This is the
    one row in the module that is a judgement rather than a transcription of the
    ticket, and it is a narrow one: the ticket says the refusal is about the URL's
    *host*, and this is that host.

    **The mutation this kills:** `url.netloc.split(":")[0] == "mock-idp"`, which
    does not fold case, as against `urlsplit(url).hostname`, which does. Written as
    its own test rather than as a row above so that a dispute about the reading
    costs one test rather than five.
    """
    configure(
        monkeypatch,
        {
            ENVIRONMENT_VARIABLE: "production",
            **deployment(
                **{OIDC_TOKEN_ENDPOINT_VARIABLE: f"http://{MOCK_SERVICE.upper()}:8000/oidc/token"}
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

    **The mutation this kills:** an f-string refusal built from the offending URL.
    """
    offending = f"http://{MOCK_SERVICE}:8000/oidc/token?tenant=e0-39"
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


def test_a_localhost_provider_is_accepted_in_a_deployment(
    configured_env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`localhost` is deliberately outside the catalog, and this is what says so.

    ADR 0077 has to justify the exclusion; this asserts it, so that a later widening
    is a red test and a reviewed decision rather than a quiet tightening. The
    reasoning is that inside a deployed container `localhost` cannot resolve to the
    mock — it is that container itself — so refusing it would refuse a provider
    running beside the application, which is a supported deployment, while
    protecting nothing.

    It is also the development stack's own `OIDC_AUTHORIZATION_ENDPOINT`
    (`http://localhost:8081/oidc/authorize`), because the browser reaches the mock
    on a published port. So a rule that swept `localhost` in would refuse the one
    setting whose development value is *not* a service name, which is the shape a
    reader of `.env.example` is most likely to add.

    **The mutation this kills:** `localhost` or `127.0.0.1` added to the catalog.
    """
    configure(
        monkeypatch,
        {
            ENVIRONMENT_VARIABLE: "production",
            **deployment(
                **{
                    OIDC_AUTHORIZATION_ENDPOINT_VARIABLE: "http://localhost:8081/oidc/authorize",
                    OIDC_TOKEN_ENDPOINT_VARIABLE: "http://127.0.0.1:8081/oidc/token",
                }
            ),
        },
    )

    settings = load_settings_class()()

    assert settings is not None, (
        "`Settings()` refused a provider on this machine. Inside a deployed container `localhost` "
        "is that container, so it cannot reach the mock and the refusal protects nothing while "
        "refusing a provider running alongside the application (ADR 0077)."
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

    `mock_idp_service` is `tests/conftest.py`'s single answer to "what is the mock
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
