"""The provider key: where it comes from, and where it may never go — ticket E0-13.

E0-13's scope: "Provider configuration from `Settings`: base URL, model, and a
masked key. **The key is a secret** — follow `CLAUDE.md`." Two of the three
arrived in E0-01; this ticket adds the third, and `.env.example` has been holding
its place since then — "the provider key is not read yet — the gateway and its
masked key land in E0-13".

The ticket's definition of done sends the security review after one thing first:
"Review for the provider key reaching a log or an error message." That is what
most of this module asserts, in the two places a settings object hands its
contents to something that writes them down — the standard serialisations, and
the exception a refused configuration raises. Its last test covers the ticket's
seventh acceptance criterion, which is about a different secret in a different
place: no `secrets.*` reference added to a workflow.

**A credential may not arrive through the URL at all**, which a second review pass
found the transport rule missing: it gated on the key *variable* being set, so
`http://user:pass@host/v1` with no key configured met no check — and httpx turns
userinfo into a real `Authorization: Basic` header, so the credential went out on
the wire and, the field being a plain `str`, rendered in `repr(settings)` and
`model_dump()` on the way. It is now refused outright, over https and on loopback
too. That is the stronger rule and also the cheaper one: it keeps the field a
plain displayable string, which is what §6.3 wants of a base URL, instead of
adding a second field that has to be masked.

**The transport rule arrived from the first review**, and it is the other half of
"the key is a secret": a key masked in every log and then sent in clear over a
network is a key in the open. Plain HTTP stays legal to this machine, where a local model
server needs no TLS and there is no network to read anything off. The refusal is
asserted **through `create_app()`**, because a `Settings` validator's own message
never reaches the operator — the startup report is built from the field name, the
field's static `description` and pydantic's error code, so asserting on a message
the validator raises would be asserting on something nobody sees.

**Off this machine means `https`, credential or not** — E0-37 item 12, decided by
Todd on 2026-08-18, and it narrows what this file used to assert. The rule gated
on a key being configured, so a base URL naming another host over plain `http`
was accepted whenever no key was set: the vLLM-in-a-cluster deployment, which
`README.md`, `.env.example` and the validator's own docstring all offered as
supported. The key is not the only thing on that connection. The student's
comment is in the body of every request the gateway makes, and §10 does not allow
it to cross a network in the clear — so the cluster case is served by terminating
TLS at the model or by running it alongside the application, and every transport
case below is therefore parametrized over a key being set and not set. The
without-a-key half of the refusal is the one that was legal until E0-37; the
without-a-key halves of the two acceptances are what stop the fix being "refuse
everything that has no key".

**E2-07 makes the transport rule read `ENVIRONMENT`, and adds a second rule beside
it.** The stack now ships a mock AI provider and `.env.example` points
`AI_PROVIDER_BASE_URL` at `http://mock-ai:8000/v1`, which the rule above refused
unconditionally — so acceptance criteria 1 and 4 of that ticket are unsatisfiable
without a change here. The change is the one the identity provider already
carries (ADR 0077, `tests/unit/test_oidc_provider_configuration.py`): cleartext
off this machine is refused *outside development*, and a URL whose host is the
mock is refused outside development too. Both halves are needed. Without the
environment condition the development stack does not start; without the mock-name
rule a deployment that forgot the variable is pointed at a container the base
Compose file starts in every deployment, which is what ADR 0077 found for the
identity provider and refused to leave standing for it.

**The configuration split of 2026-09-02 moves one of those two rules and doubles
several others, and the ruling rather than any new test is the reason.** The real
provider and the in-repo mock now have a triple each —
`AI_PROVIDER_{API_KEY,BASE_URL,MODEL_NAME}` and
`MOCK_AI_PROVIDER_{API_KEY,BASE_URL,MODEL_NAME}` — `AIGateway` takes a `live`
flag, and selection is settled: `live=False` reads the mock triple in development
and test, `live=True` reads the real triple in every environment. Three
consequences land in this file, and the second is a strengthening rather than a
rename:

- **Two keys, so every rule about "the key" becomes two rules.** The discovery
  design does not change — neither variable is written down here — but what is
  found is now a key per side, and a rule that held for one of them and not the
  other would be a masked credential beside an unmasked one. The sides are told
  apart by the `MOCK_` prefix the ruling gives them, which keeps the finding
  derived rather than transcribed.
- **The catalog rule gets stricter: the real triple refuses the `mock-ai` host in
  *every* environment, development included.** It used to be conditioned on the
  environment, and the whole reason was that `.env.example` had one base URL and
  pointed it at the mock so the development stack could classify. That value now
  lives on `MOCK_AI_PROVIDER_BASE_URL`, so the exemption has nothing left to
  protect — and the eval runner reads the real triple on a developer's machine
  too, where a `mock-ai` address would measure a character count and record it as
  SPEC §9.3's floor.
- **The mock triple is unread outside development and test, which in this module
  is visible as an absence:** the catalog rule and the transport rule are rules
  about the real base URL, and `MOCK_AI_PROVIDER_BASE_URL` naming the mock in a
  deployment is not refused, because nothing there reads it. Asserted as a pair
  with the line above, since a rule that refused both would take the development
  stack down and one that refused neither would be no rule at all.

**What this module cannot see, and where it is seen instead.** That a
`live=False` gateway in a deployment actually *reads* the real triple, and that a
`live=True` one reads it in development, are properties of the gateway rather
than of `Settings`, and nothing here builds a gateway.
`tests/unit/test_the_gateway_reads_the_provider_triple_the_flag_selects.py`
builds one, points the two triples at two loopback endpoints and asks which of
them was called; the flag the eval runner passes to its own is asserted in
`tests/unit/test_the_eval_runner_builds_a_live_gateway.py`. The division is worth
knowing when one of the three goes red: a rule can attach to the wrong variable
here while selection is perfectly correct there, and the reverse.

**So every test whose subject is one of those two rules states the environment it
runs under** (`docs/MISTAKES.md` entry 40), and each is written so that exactly
one rule can be what fires: the mock-name rows carry `https`, because a cleartext
mock address is refused by either rule and a test that could not say which would
be green for a reason unrelated to what it asserts. The rest of this module —
the masking rules, the userinfo rules, the needles — runs under `.env.example`'s
documented `development` through `configured_env`, and says so here rather than
in each test, because none of them turns on the value.

**The key's variable is not named here.** E0-13 spells no variable and no field,
so both are found — the `.env.example` entry by the words in its name, and the
`Settings` field by the words in *its* name — and one test requires the two to be
the same thing. That interlock is the point: a field that resolves some other
variable, or an entry no field reads, is the shape
`tests/unit/test_env_example_sync.py` exists for, and this file would otherwise
be asserting masking on a value nothing configures.

**The needle is asserted, not chosen.** Every leak rule here searches a rendering
for fragments of one fake value, and the first version of that value shared the
word `provider` with the field names being rendered — so all seven serialisation
rules were false for every possible implementation, and their failure looked
exactly like a leaked key. The implementer disputed it and an arbitrator ruled
the test wrong. Two controls now hold the property the value has to have: one
renders a `Settings` that was never given the needle, one renders a refusal that
was never given it, and both require zero fragments. The rule they encode is that
**a colliding needle is repaired by changing the needle** — never by raising
`LEAK_FRAGMENT_LENGTH`, which is shared with two other modules and protects real
database passwords there.

**Why this is not folded into `tests/unit/test_config_settings.py`.** Every rule
there is driven by a pair of mappings from a variable to the password *inside a
URL*, with an interlock holding the two in step, and a bare key has no URL to sit
in. Adding a fourth kind of entry to those mappings would make each of them mean
two things. The cost of a separate module is that the list of serialisation
surfaces below is a second copy of that file's; it is named as such where it is
written, and it is a list of pydantic's public API rather than a rule that can
drift into being wrong.
"""

import contextlib
import json
import re
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"

# **This suite's choice**, and how the provider key is recognised without E0-13
# having spelled it. The same two lists, for the same reason, as
# `tests/integration/test_ai_gateway_validity_roundtrip.py` — a rename is a
# one-line change in each, and a pull request that renames it says so.
PROVIDER_KEY_WORDS = ("KEY", "TOKEN", "SECRET", "CREDENTIAL")
PROVIDER_KEY_QUALIFIERS = ("AI", "PROVIDER", "MODEL", "LLM")

# The needle every leak assertion below searches for.
#
# **The property it has to have is not "long and unlikely-looking". It is that it
# shares no run of `LEAK_FRAGMENT_LENGTH` characters with anything these
# assertions legitimately render.** The first version of this constant was
# `fake-ai-provider-Qv7ZmXt4Ld9RbNsW`, chosen for the first property and failing
# the second: `provider` is an eight-character window of it, and every rendering
# of `Settings` already contains that word — in the field name
# `ai_provider_base_url` E0-01 shipped, in the key field's own name, and in the
# `.env.example` placeholder `https://api.example-provider.test/v1` that
# `configured_env` sets. The assertion was therefore false for every possible
# implementation, including the correctly masked `SecretStr` in the tree, and the
# "leak" it reported was the English word "provider". The implementer disputed it
# and an arbitrator ruled the test wrong.
#
# Two things follow, and they are the repair rather than the value.
# `test_the_needle_matches_nothing_settings_renders_without_it` below makes the
# property an asserted invariant instead of a choice someone made carefully once,
# and the readable label lives in the constant's *name* rather than in its value —
# the failure messages name `FAKE_PROVIDER_CREDENTIAL` so a reader still knows
# what the fragments belong to.
#
# Nothing here resembles a real credential and nothing was copied from a working
# `.env` (CLAUDE.md, secrets). Named `...CREDENTIAL` rather than `...KEY` so
# ruff's S105 keeps flagging the real thing; `tests/fixtures/database.py` made
# the same choice.
FAKE_PROVIDER_CREDENTIAL = "Qv7ZmXt4Ld9RbNsW-Kj3PxE8mZt5UwGh"

# Length of the contiguous run of a secret that counts as leaked. Checking for the
# whole value is not enough: pydantic elides the middle of a long repr, so a leak
# can print all but one character and still not contain the exact string.
# Truncation is not redaction. Same length and same reason as
# `tests/unit/test_config_settings.py`.
#
# **Raising it is not a way to fix a colliding needle**, and the arbitrator who
# ruled on that collision measured that 10 would also have turned this module
# green. It is a safety threshold shared with `test_config_settings.py` and
# `test_db_engine_configuration.py`: at 10, a rendering that truncated a real
# database password to nine characters passes all three. Tune the needle, never
# this.
LEAK_FRAGMENT_LENGTH = 8

# A required deployment variable, removed to force a configuration failure so the
# error it raises can be searched. Its own absence is E0-01's subject; here it is
# only the cause of an exception that has the provider key in scope.
REQUIRED_DEPLOYMENT_VARIABLE = "DATABASE_URL"

# The base URL, and the shapes the transport rule has to sort. `.env.example`
# already names the whole range of deployments this has to serve: "a hosted
# provider, a proxy, or a local server such as vLLM or Ollama".
#
# **Two of them since the split.** The first is the real provider's and is the
# subject of every transport and catalog rule below. The second is the mock's, and
# it is here for exactly one pair of tests: the development stack points it at
# `mock-ai`, and a deployment may leave it pointed there because nothing outside
# development and test reads it.
AI_PROVIDER_BASE_URL_VARIABLE = "AI_PROVIDER_BASE_URL"
MOCK_AI_PROVIDER_BASE_URL_VARIABLE = "MOCK_AI_PROVIDER_BASE_URL"

# How a found key variable or field says which provider it describes. The ruling
# gives the mock's triple this prefix, so the side is derived from the name rather
# than transcribed — which is what keeps the discovery design in this file intact:
# neither variable is written down, and what is written down is the one thing the
# ruling fixes about both.
MOCK_VARIABLE_PREFIX = "MOCK_"

# The two sides, as labels a failure message can name. Written out so that "one
# key per side" is a closed set rather than however many happen to be found.
REAL_SIDE = "the real provider"
MOCK_SIDE = "the in-repo mock"
PROVIDER_SIDES = (REAL_SIDE, MOCK_SIDE)

# A host that is certainly not this machine — and a needle as well as a host,
# because the refusal must quote neither the URL nor the key. It has to share no
# eight-character run with the field name, with the field's own `description`, or
# with pydantic's error code, and
# `test_the_refusal_of_an_insecure_provider_url_names_the_variable_and_quotes_nothing_else`
# runs a control that says it does not.
OFF_MACHINE_HOST = "qv7zmxt4ld9rbnsw.test"
OFF_MACHINE_HTTPS_URL = f"https://{OFF_MACHINE_HOST}/v1"
OFF_MACHINE_HTTP_URL = f"http://{OFF_MACHINE_HOST}/v1"

# Plain HTTP is safe to exactly one place: this machine, where there is no network
# for anything to be read off. All three spellings, because a rule written against
# the address alone refuses a developer running Ollama on `localhost`, and one
# written against the name alone refuses the address — and each of those is a
# working local setup turned away at startup with a security message.
LOOPBACK_HTTP_URLS = (
    "http://127.0.0.1:11434/v1",
    "http://localhost:11434/v1",
    "http://[::1]:11434/v1",
)

# The variable that decides which of E2-07's two new rules apply, and the
# environments that are not the development one. Two rows rather than four:
# *which* names count as a deployment is settled once, by
# `tests/unit/test_oidc_provider_configuration.py::test_a_url_addressing_the_mock
# _is_refused_outside_development`, whose four rows include the two near misses a
# one-line condition gets wrong (`development-blue`, `pre-development`). Repeating
# them under every rule here would be four copies of one assertion.
ENVIRONMENT_VARIABLE = "ENVIRONMENT"
DEPLOYMENT_ENVIRONMENTS = ("production", "staging")

# The mock provider's Compose service name — the name by which a container on this
# stack reaches it, and the whole of what the catalog rule refuses.
#
# Written out here rather than derived, exactly as `MOCK_SERVICE` is in
# `test_oidc_provider_configuration.py`: it is the subject of the rule, and a
# second entry belongs in a reviewed diff on this line. It is held against reality
# by `test_the_refused_provider_host_is_the_compose_service_name_the_mock_runs_as`
# below, because a written-out catalog can go stale without anything failing — a
# rule that refuses a name nothing runs under reports every configuration clean
# (`docs/MISTAKES.md` entry 35).
MOCK_AI_SERVICE = "mock-ai"

# Ways of addressing the mock, one per spelling, because a rule that matches the
# development stack's exact string is not a rule about the host. All `https`, so
# that only the catalog can be what refuses them: a cleartext mock address is
# refused by the transport rule too, and a row that two rules both refuse cannot
# say which one fired.
MOCK_AI_URL_SPELLINGS = {
    "the development stack's address over TLS": f"https://{MOCK_AI_SERVICE}:8000/v1",
    "no port": f"https://{MOCK_AI_SERVICE}/v1",
    "another port": f"https://{MOCK_AI_SERVICE}:8443/v1",
    "no path": f"https://{MOCK_AI_SERVICE}",
}

# The other direction: URLs that contain the service name and address something
# else entirely. Each is an address a real institution could hold, and each is
# refused by the substring rule that is the obvious way to write the check.
NON_MOCK_AI_URL_SPELLINGS = {
    "the service name as a subdomain": f"https://{MOCK_AI_SERVICE}.example.edu/v1",
    "a host the service name prefixes": f"https://{MOCK_AI_SERVICE}-2.example.edu/v1",
    "a host the service name ends": f"https://staging-{MOCK_AI_SERVICE}/v1",
    "the service name in the path": f"https://ai.example.edu/{MOCK_AI_SERVICE}/v1",
}

# The development stack's own value, cleartext to a service name that is not this
# machine — refused by the old rule unconditionally, and the configuration E2-07's
# first and fourth acceptance criteria both run from.
DEVELOPMENT_MOCK_AI_URL = f"http://{MOCK_AI_SERVICE}:8000/v1"

# A username and a password written into the URL. Both are needles as well as
# credentials: the refusal has to quote neither, so neither may share an
# eight-character run with the field name, with the field's own `description`, or
# with pydantic's error code — and the test asserting that silence runs a control
# saying they do not.
USERINFO_USER = "Kj3PxE8mZt5UwGh"
USERINFO_CREDENTIAL = "Tf2YcRbVn8LqxWd"

# The four shapes a credential can arrive in through the URL, and they are four
# rather than one because the rule that let this through was conditional. The
# scheme check gated on the key *variable* being set, so a URL carrying its
# credential **instead of** setting that variable met no check at all — and httpx
# turns userinfo into a real `Authorization: Basic` header, so the credential left
# the process exactly as if it had been configured properly, and was captured at
# the server. Over https and on loopback too, because the field must never hold a
# secret at all: that is what keeps it a plain displayable `str`, which §6.3 wants
# (base URL shown, key masked), rather than a second field needing masking of its
# own — and a plain `str` renders its password in `repr(settings)` and
# `model_dump()`, which is how this one did.
USERINFO_URLS = {
    "https, off machine": f"https://{USERINFO_USER}:{USERINFO_CREDENTIAL}@{OFF_MACHINE_HOST}/v1",
    "http, loopback": f"http://{USERINFO_USER}:{USERINFO_CREDENTIAL}@127.0.0.1:11434/v1",
    "https, username only": f"https://{USERINFO_USER}@{OFF_MACHINE_HOST}/v1",
    "https, empty password": f"https://{USERINFO_USER}:@{OFF_MACHINE_HOST}/v1",
}

# The repository secrets a workflow may reference today. `GITHUB_TOKEN` is
# supplied by Actions itself rather than configured, so it is not a stored secret
# in the sense CLAUDE.md's policy is about. Everything else is Todd's call, in
# advance and in writing.
#
# **`AI_PROVIDER_API_KEY` was added on 2026-09-02, and this entry is the record of
# the agreement rather than a convenience.** The secret exists in the repository,
# the written go was given by the repository owner in conversation that day, and
# the reference it authorises is exactly one: the `env:` block of the eval runner
# step in `.github/workflows/ci.yml`. E2-12's scope made the sequencing a named
# part of the work — "asked, then waited for, never provisional" — and its third
# acceptance criterion requires the go to be quoted in the pull request before the
# reference exists in the diff.
#
# The base URL and the model name beside it are deliberately *not* secrets:
# `.env.example` documents both in the open, and keeping them readable is half of
# what makes one floor measurement comparable to the next (ADR 0031).
#
# **A name, never a pattern.** This check goes on refusing the next unagreed
# reference exactly as it refused this one; widening it to match a shape would
# give up the property it exists for. Dispute E2-12-03 records the ruling and the
# direction it settles — a set that grows by one reviewed name is the mechanism
# working, not a hole in it.
PERMITTED_WORKFLOW_SECRETS = frozenset({"GITHUB_TOKEN", "AI_PROVIDER_API_KEY"})

# `${{ secrets.NAME }}`, in any of the spacings a workflow writes it.
SECRET_REFERENCE = re.compile(r"\$\{\{\s*secrets\.([A-Za-z_][A-Za-z0-9_]*)")

# A string certainly present in any GitHub Actions workflow that uses expressions
# at all. The canary for the search above: a regex that matches nothing and a
# directory that was never read report the same emptiness (`docs/MISTAKES.md`
# entry 3, third case — a pattern that went green against the exact text it
# existed to catch).
WORKFLOW_CANARY = "${{"


def load_settings_class() -> type:
    """Import `Settings` inside the test, so a missing module fails one test loudly."""
    from app.config import Settings

    return Settings


def load_configuration_error() -> type[BaseException]:
    """The error type the application promises its callers, imported inside the test.

    The same loader, spelled the same way, as
    `tests/unit/test_create_app_startup_errors.py`. That module owns the claim
    that bad configuration *reaches a caller* as this type and that pydantic's own
    error does not escape; this one only names the type so that a refusal asserted
    here is a configuration refusal rather than whatever happened to come out.

    Worth separating, because the two could read as duplication. Owning the
    startup surface is "every shape of bad configuration arrives as one type".
    Naming it here is narrower and is about this file's own assertions: it is what
    stops `pytest.raises` being satisfied by an `AttributeError` raised because a
    symbol moved, which is a broken test reading as a rule that fired.
    """
    from app.config import ConfigurationError

    return ConfigurationError


def development_environment() -> str:
    """The `ENVIRONMENT` value that means development, read from its one definition.

    Out of `app.config` rather than written here, because E0-37 item 2 made that
    constant the single definition site and a literal in this module would be one
    more copy of the value that item exists to remove. Spelled exactly as
    `tests/unit/test_oidc_provider_configuration.py` spells it.
    """
    from app.config import DEVELOPMENT_ENVIRONMENT

    assert isinstance(DEVELOPMENT_ENVIRONMENT, str) and DEVELOPMENT_ENVIRONMENT, (
        "`app.config.DEVELOPMENT_ENVIRONMENT` is not a non-empty string, so this module cannot "
        "tell which environment the mock provider is permitted in."
    )
    return DEVELOPMENT_ENVIRONMENT


def side_of(name: str) -> str:
    """Which provider a found key variable or field describes.

    The `MOCK_` prefix the configuration split gives the mock's triple, and
    nothing else. Derived rather than transcribed so that this file goes on
    *finding* the keys instead of naming them — the interlock below is only worth
    anything because neither name is written here.
    """
    return MOCK_SIDE if name.upper().startswith(MOCK_VARIABLE_PREFIX) else REAL_SIDE


def documented_key_variables(documented_env: Mapping[str, str]) -> list[str]:
    """Every `.env.example` entry whose name reads as an AI provider key."""
    return sorted(
        name
        for name in documented_env
        if any(word in name.upper() for word in PROVIDER_KEY_WORDS)
        and any(word in name.upper() for word in PROVIDER_KEY_QUALIFIERS)
    )


def documented_key_variables_by_side(documented_env: Mapping[str, str]) -> dict[str, str]:
    """The documented key entry for each side, or a failure naming what was found.

    Exactly one per side. Two entries on one side is an ambiguity this file cannot
    resolve — every masking rule below would have to pick one — and a side with
    none is a provider whose credential nothing documents, which is the state
    `tests/unit/test_env_example_sync.py` exists to refuse from the other
    direction.
    """
    found: dict[str, list[str]] = {side: [] for side in PROVIDER_SIDES}
    for name in documented_key_variables(documented_env):
        found[side_of(name)].append(name)

    wrong = {side: names for side, names in found.items() if len(names) != 1}
    if wrong:
        pytest.fail(
            f"`.env.example` documents {dict(found)} as AI provider keys, and this file needs "
            "exactly one per side.\n"
            "\n"
            "The configuration split of 2026-09-02 gives the real provider and the in-repo mock a "
            "triple each, so there are two credentials to mask rather than one, and every leak "
            "rule below is asserted about both. A side with no entry is a provider whose key "
            "nothing documents; a side with two is an ambiguity this file cannot resolve, and the "
            "pull request should say what the second is for.\n"
            "\n"
            "If a key is spelled with a word `PROVIDER_KEY_WORDS` does not reach, or a side is "
            "marked some way other than the `MOCK_` prefix, those two constants at the top of this "
            "file are the lines that change."
        )
    return {side: names[0] for side, names in found.items()}


def settings_key_fields(settings_cls: type) -> dict[str, Any]:
    """Every `Settings` field whose name reads as the AI provider key."""
    fields = getattr(settings_cls, "model_fields", {})
    return {
        name: info
        for name, info in fields.items()
        if any(word in name.upper() for word in PROVIDER_KEY_WORDS)
        and any(word in name.upper() for word in PROVIDER_KEY_QUALIFIERS)
    }


def variable_for(name: str, info: Any) -> str:
    """The environment variable a `Settings` field resolves.

    pydantic-settings uppercases the field name unless the field declares an
    alias, and this project uses no prefix — `database_url` reads `DATABASE_URL`.
    An alias is read if there is one, so a field naming its variable explicitly is
    followed rather than guessed at.
    """
    alias = getattr(info, "validation_alias", None) or getattr(info, "alias", None)
    if isinstance(alias, str) and alias:
        return alias.upper()
    return name.upper()


def key_fields_by_side(settings_cls: type) -> dict[str, tuple[str, Any]]:
    """The provider-key field for each side, or a failure naming the criterion.

    Exactly one per side, for the reason `documented_key_variables_by_side` gives:
    a rule that masked one credential and not the other would ship a masked key
    beside an unmasked one, and every leak assertion in this module would report
    the tree clean.
    """
    fields = settings_key_fields(settings_cls)
    found: dict[str, list[str]] = {side: [] for side in PROVIDER_SIDES}
    for name in fields:
        found[side_of(name)].append(name)

    wrong = {side: names for side, names in found.items() if len(names) != 1}
    if wrong:
        pytest.fail(
            f"`Settings` has {dict(found)} fields that read as an AI provider key; it declares "
            f"{sorted(getattr(settings_cls, 'model_fields', {}))}, and this file needs exactly one "
            "per side.\n"
            "\n"
            "E0-13's scope: 'Provider configuration from `Settings`: base URL, model, and a "
            "masked key', and the epic README adds that an '`.env.example` entry needs a "
            "`Settings` field resolving it before the sync test will accept it'. The "
            "configuration split of 2026-09-02 makes that two providers rather than one.\n"
            "\n"
            "If a field is spelled with a word `PROVIDER_KEY_WORDS` does not reach, or a side is "
            "marked some way other than the `MOCK_` prefix, those two constants at the top of "
            "this file are the lines that change."
        )
    return {side: (names[0], fields[names[0]]) for side, names in found.items()}


def real_key_field(settings_cls: type) -> tuple[str, Any]:
    """The real provider's key field.

    Named separately because `configure_provider` below needs exactly it: every
    transport and catalog rule in this module is a rule about the *real* base URL,
    so the key that travels with it is the real one.
    """
    return key_fields_by_side(settings_cls)[REAL_SIDE]


def leaked_fragments(text: str, secret: str, size: int = LEAK_FRAGMENT_LENGTH) -> list[str]:
    """Every contiguous run of `secret` of length `size` that appears in `text`."""
    windows = (secret[start : start + size] for start in range(len(secret) - size + 1))
    return sorted({window for window in windows if window in text})


def render(value: object) -> str:
    """Both renderings of an arbitrary object, because a mask can cover one only.

    A wrapper whose `__str__` masks and whose `__repr__` does not is still a leak,
    and so is the reverse: `logging` formats with `%s`, while `pprint` and a bare
    `print` of a dict reach for `repr`.
    """
    renderings = [repr(value)]
    with contextlib.suppress(TypeError, ValueError):  # not JSON-serialisable
        renderings.append(json.dumps(value, default=str))
    return "\n".join(renderings)


# Every standard way a pydantic model turns itself into data, each named as the
# call site would spell it so a failure says which one leaked. **A second copy of
# the list in `tests/unit/test_config_settings.py`**, and deliberately so: it is
# pydantic's public API, chosen by the ticket that chose pydantic-settings, rather
# than a rule about this project that could drift.
SERIALISATIONS: dict[str, Callable[[Any], str]] = {
    "str(settings)": str,
    "repr(settings)": repr,
    "settings.model_dump()": lambda settings: render(settings.model_dump()),
    'settings.model_dump(mode="json")': lambda settings: render(settings.model_dump(mode="json")),
    "settings.model_dump_json()": lambda settings: str(settings.model_dump_json()),
    "dict(settings)": lambda settings: render(dict(settings)),
    "iteration over settings": lambda settings: render(list(settings)),
}


def revealed(value: object) -> str:
    """The configured value, whatever the field wrapped it in.

    Mechanism-agnostic within one limit worth naming: a plain value is read with
    `str()`, and anything offering pydantic's secret protocol with
    `get_secret_value()`. It requires neither. If a field masks itself some third
    way, this helper is what needs widening — not the assertion, which is only
    that the application can still read what it was configured with.
    """
    getter = getattr(value, "get_secret_value", None)
    return getter() if callable(getter) else str(value)


def exception_chain(failure: BaseException) -> list[BaseException]:
    """`failure` and everything it was raised from, `__cause__` and `__context__` alike."""
    chain: list[BaseException] = []
    current: BaseException | None = failure
    while current is not None and not any(link is current for link in chain):
        chain.append(current)
        current = current.__cause__ or current.__context__
    return chain


# ---------------------------------------------------------------------------
# The field, and the entry it resolves
# ---------------------------------------------------------------------------


def test_settings_resolves_the_documented_provider_key_variable(
    configured_env: dict[str, str],
    documented_env: dict[str, str],
) -> None:
    """The key arrives through `Settings`, from the entry `.env.example` documents.

    Two halves of one sentence, asserted together because the way this fails is
    that they come apart. The epic README's settled rule is that "an `.env.example`
    entry needs a reader, or its test fails" — a field resolving some *other*
    variable satisfies `test_env_example_sync.py` in one direction while leaving
    the documented entry read by nothing, and every masking assertion below would
    then be made about a value the application never sees.

    Neither name is written into this file. The entry is found by the words in its
    name and the field by the words in its own, and what is asserted is that they
    meet.

    **The interlock is per side since the configuration split of 2026-09-02**, and
    the guarantee is unchanged rather than weakened: there are two credentials
    now, and each one's documented entry has to be the variable its own field
    reads. A single interlock over two keys would be satisfied by a real-provider
    field resolving the mock's entry, which is a masked credential meeting the
    wrong documentation.
    """
    assert documented_env, "`.env.example` is missing or parsed to nothing."

    entries = documented_key_variables_by_side(documented_env)
    fields = key_fields_by_side(load_settings_class())

    mismatched: list[str] = []
    for side in PROVIDER_SIDES:
        name, info = fields[side]
        resolved = variable_for(name, info)
        if resolved != entries[side]:
            mismatched.append(
                f"  {side}: `Settings.{name}` resolves {resolved!r}, `.env.example` documents "
                f"{entries[side]!r}"
            )

    assert not mismatched, "\n".join(
        [
            "A provider key's field and its documented entry are not the same variable:",
            *mismatched,
            "",
            "An entry no setting reads is an entry that documents nothing, and a field reading a "
            "variable the file does not document is configuration nobody can find (ADR 0008). "
            "Every masking assertion below would then be made about a value the application "
            "never sees.",
        ]
    )


def test_the_provider_key_is_still_readable_by_the_application(
    configured_env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Masking hides the value from serialisation, not from the code that needs it.

    The other half of the property, and the reason it is not enough to assert
    that the key is nowhere to be found: deleting the field, or storing a
    permanently redacted string, satisfies that on its own and leaves every hosted
    provider unreachable. It is `docs/MISTAKES.md` entry 23 in advance — a value
    validated, masked, and read by nothing.

    **Both keys, since the configuration split of 2026-09-02.** A gateway built
    `live=True` authenticates with the real provider's and one built `live=False`
    in development with the mock's, so a key readable on one side and redacted on
    the other leaves exactly one of those two unable to reach anything — and which
    one depends on the environment, which is the hardest kind of failure to see.
    """
    settings_cls = load_settings_class()
    fields = key_fields_by_side(settings_cls)
    for name, info in fields.values():
        monkeypatch.setenv(variable_for(name, info), FAKE_PROVIDER_CREDENTIAL)

    settings = settings_cls()

    unreadable = [
        f"  {side}: `settings.{name}` holds {getattr(settings, name)!r}"
        for side, (name, _) in fields.items()
        if FAKE_PROVIDER_CREDENTIAL not in revealed(getattr(settings, name))
    ]
    assert not unreadable, "\n".join(
        [
            "These provider keys no longer carry the value they were configured with:",
            *unreadable,
            "",
            "Hiding a credential from serialisation must not hide it from the code that "
            "authenticates with it, or the gateway reaches no provider at all on that side.",
        ]
    )


@pytest.mark.parametrize("surface", list(SERIALISATIONS))
def test_the_provider_key_does_not_appear_in_settings_serialisation(
    configured_env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    surface: str,
) -> None:
    """The masked half of "base URL, model, and a masked key".

    The settings object lives on `app.state` for the process lifetime and gets
    handed to whatever wants to describe the running configuration: a structured
    log line at startup, an error report, §6.3's admin configuration view. SPEC
    §10 requires secrets to stay in the environment or the secret store, and a
    settings object that hands the provider key to `model_dump()` puts it in the
    log aggregator instead.

    Asserted per surface rather than in one test, because a guard that covers
    `str()` and not `model_dump()` should report exactly that. Fragments rather
    than the whole value, because an elided rendering can print all but one
    character and still not contain it.

    **Two guards, and the second is the one this test was ruled wrong for
    lacking.** The first is that the field took the value, since a rendering of a
    settings object that never held the key contains no key however bad the
    masking is. The second is
    `test_the_needle_matches_nothing_settings_renders_without_it` below: without
    it, a needle sharing a word with the field names being rendered makes this
    assertion false for every possible implementation, and the failure reads
    exactly like a leak.

    **Both keys are configured with the needle, since the configuration split of
    2026-09-02.** One rendering, two credentials in it, and any fragment found is
    reported whichever side it came from — because a `model_dump()` that masks the
    real provider's key and prints the mock's is still a credential in the log
    aggregator, and the mock's key is a real credential wherever somebody points
    that triple at something other than the in-repo mock.
    """
    settings_cls = load_settings_class()
    fields = key_fields_by_side(settings_cls)
    for name, info in fields.values():
        monkeypatch.setenv(variable_for(name, info), FAKE_PROVIDER_CREDENTIAL)

    settings = settings_cls()
    untaken = [
        f"  {side}: `settings.{name}` holds {getattr(settings, name)!r}, and this test set "
        f"{variable_for(name, info)!r}"
        for side, (name, info) in fields.items()
        if FAKE_PROVIDER_CREDENTIAL not in revealed(getattr(settings, name))
    ]
    assert not untaken, "\n".join(
        [
            "These fields did not take the value this test configured, so the rendering below "
            "would contain no key whatever the masking does:",
            *untaken,
            "",
            "That is a gap in this file — or a field reading a variable it does not document — "
            "rather than a leak that was avoided.",
        ]
    )

    rendered = SERIALISATIONS[surface](settings)
    fragments = leaked_fragments(rendered, FAKE_PROVIDER_CREDENTIAL)
    assert not fragments, (
        f"{surface} contains fragments of `FAKE_PROVIDER_CREDENTIAL`, the value this test "
        f"configured the AI provider key with: {fragments}. E0-13's scope calls it a masked key "
        "and its definition of done sends the security review after 'the provider key reaching a "
        "log or an error message'. The full text was:\n"
        f"{rendered}\n"
        "If these fragments look like ordinary words rather than like the key, suspect the needle "
        "before the masking: `test_the_needle_matches_nothing_settings_renders_without_it` is the "
        "test that answers that question, and it should be red beside this one."
    )


@pytest.mark.parametrize("surface", list(SERIALISATIONS))
def test_the_needle_matches_nothing_settings_renders_without_it(
    configured_env: dict[str, str],
    surface: str,
) -> None:
    """`FAKE_PROVIDER_CREDENTIAL` shares no fragment with a `Settings` that never held it.

    Not a test of the ticket — a test of the needle every leak assertion in this
    module is driven by, and the one whose absence cost a dispute round. The
    original needle contained the word `provider`, which appears in
    `ai_provider_base_url`, in the key field's own name and in the `.env.example`
    placeholder for the base URL. Every rendering of `Settings` therefore
    contained an eight-character run of the needle before any masking was
    considered, so the leak assertions above could not pass against any
    implementation at all — and their failure was indistinguishable from a real
    leak, which is why it was read as one.

    `configured_env` supplies `.env.example`'s own placeholders and nothing else,
    so the object rendered here holds whatever the file documents for the provider
    key and never the needle. Anything found is a collision between the needle and
    the vocabulary of the thing being searched.

    It is the discipline `WORKFLOW_CANARY` already applies further down this file,
    in the direction that matters more: a canary says a search that found nothing
    really looked, and this says a search that found something really found the
    thing it was looking for.
    """
    settings = load_settings_class()()
    rendered = SERIALISATIONS[surface](settings)

    assert leaked_fragments(rendered, FAKE_PROVIDER_CREDENTIAL) == [], (
        f"`FAKE_PROVIDER_CREDENTIAL` shares "
        f"{leaked_fragments(rendered, FAKE_PROVIDER_CREDENTIAL)} with {surface} of a `Settings` "
        "that was never given it. Every leak assertion in this module is therefore false for "
        "every implementation, and each one reports an ordinary word as a leaked credential. The "
        "repair is the needle, not the threshold: choose a value sharing no run of "
        f"{LEAK_FRAGMENT_LENGTH} characters with what is rendered here, and leave "
        "`LEAK_FRAGMENT_LENGTH` alone — it is shared with `test_config_settings.py` and "
        "`test_db_engine_configuration.py`, where raising it would let a truncated database "
        f"password through. The full text was:\n{rendered}"
    )


def test_a_refused_configuration_does_not_print_the_provider_key(
    configured_env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The other surface a secret escapes through: the error a bad configuration raises.

    A configuration error is printed to the container startup log with its whole
    traceback, so a validation error that renders the values it was given is a
    credential in a log. The chain is searched as well as the outermost
    exception, because `raise ConfigError(...) from exc` leaves the original
    holding the values and Python prints a cause's message too — the same three
    surfaces `tests/unit/test_config_settings.py` searches, for the same reason.

    A required variable is removed to *cause* the failure, and the assertion is
    about the key rather than about that variable: `Settings` must refuse the
    configuration, and this test says so first, since an exception that was never
    raised leaks nothing.

    **This test carried the same needle collision as the serialisation tests and
    did not show it**, which is worth writing down because it is the more
    dangerous half. It passed only because the provider key field cannot currently
    fail validation; the arbitrator who ruled on the collision forced it to fail
    and it reported `['provider']`, sourced from the field's static `description=`
    string rather than from any configured value. So a validator added to that
    field in E2 would have turned this red against a correctly masked key.
    `test_the_needle_matches_nothing_a_refused_configuration_prints` below is what
    now sees that, without waiting for a validator to exist.

    **Both keys are in scope of the raised error since the configuration split of
    2026-09-02**, so both are configured with the needle here. A startup traceback
    does not distinguish them: whichever one a validator renders reaches the same
    container log.
    """
    settings_cls = load_settings_class()
    for name, info in key_fields_by_side(settings_cls).values():
        monkeypatch.setenv(variable_for(name, info), FAKE_PROVIDER_CREDENTIAL)
    monkeypatch.delenv(REQUIRED_DEPLOYMENT_VARIABLE, raising=False)

    with pytest.raises(Exception) as refused:
        settings_cls()

    for link in exception_chain(refused.value):
        for rendering, where in ((str(link), "str"), (repr(link), "repr")):
            fragments = leaked_fragments(rendering, FAKE_PROVIDER_CREDENTIAL)
            assert not fragments, (
                f"{where}() of the raised {type(link).__name__} contains fragments of "
                f"`FAKE_PROVIDER_CREDENTIAL`: {fragments}. The full text was:\n{rendering}\n"
                "If these read as ordinary words rather than as the key, the needle is what is "
                "wrong — see `test_the_needle_matches_nothing_a_refused_configuration_prints`."
            )
        errors = getattr(link, "errors", None)
        if callable(errors):
            payload = json.dumps(errors(), default=str)
            fragments = leaked_fragments(payload, FAKE_PROVIDER_CREDENTIAL)
            assert not fragments, (
                f"The structured payload of {type(link).__name__}.errors() contains fragments of "
                f"`FAKE_PROVIDER_CREDENTIAL`: {fragments}."
            )


def test_the_needle_matches_nothing_a_refused_configuration_prints(
    configured_env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The needle control for the exception surface, which renders more than the values.

    The serialisation control above renders a settings object. This renders a
    *refusal*, which reaches things a successful `model_dump()` never does: field
    names, error types, and — the case that actually bit — a field's static
    `description=`. The provider key is left at whatever `.env.example` documents,
    so nothing here has been given the needle and anything found is a collision.

    Without this, the guarantee the test above claims is unfalsifiable in one
    direction and false in the other: today it passes because that field cannot
    fail validation, and the first validator added to it in E2 turns it red
    against a perfectly masked key, with the failure reading as a credential in a
    startup log.

    **The type is deliberately not named on this path**, unlike the transport
    refusals further down, and the reason is that nobody has measured it: what
    `Settings()` raises for an *absent* variable — pydantic's error, or this
    project's conversion of it — is E0-01's business and either answer is in scope
    here, since the subject is what a refusal renders rather than what it is. What
    is not left open is the import: `load_settings_class()` is called outside the
    block, so a `Settings` that has been renamed or moved fails this test loudly
    instead of counting as a refused configuration and letting the needle search
    below run over an unrelated exception.
    """
    settings_cls = load_settings_class()
    monkeypatch.delenv(REQUIRED_DEPLOYMENT_VARIABLE, raising=False)

    with pytest.raises(Exception) as refused:
        settings_cls()

    for link in exception_chain(refused.value):
        renderings = [(str(link), "str"), (repr(link), "repr")]
        errors = getattr(link, "errors", None)
        if callable(errors):
            renderings.append((json.dumps(errors(), default=str), "errors()"))
        for rendering, where in renderings:
            found = leaked_fragments(rendering, FAKE_PROVIDER_CREDENTIAL)
            assert found == [], (
                f"`FAKE_PROVIDER_CREDENTIAL` shares {found} with {where} of a refusal that was "
                f"never given it ({type(link).__name__}). The leak assertion above is therefore "
                "false for every implementation, and it reports ordinary words as a leaked "
                "credential. Change the needle, not `LEAK_FRAGMENT_LENGTH`. The full text "
                f"was:\n{rendering}"
            )


# ---------------------------------------------------------------------------
# How the key is allowed to travel
# ---------------------------------------------------------------------------


def build_app() -> Any:
    """Call the application factory inside the test, so a missing module fails loudly.

    The same entry point `tests/unit/test_create_app_startup_errors.py` uses, and
    for the reason it gives: nothing guarantees the factory does not catch and
    re-raise, and the factory is what the caller holds. It matters more here than
    there — a `Settings` validator's own message does not reach the operator at
    all, because the report is assembled from the field name, the field's static
    `description` and pydantic's error code, so a rule that lives in a validator's
    message is a rule nobody is told about.
    """
    from app.main import create_app

    return create_app()


def renderings_of(failure: BaseException) -> dict[str, str]:
    """Every rendering of every link in a chain, labelled by where it came from."""
    surfaces: dict[str, str] = {}
    for index, link in enumerate(exception_chain(failure)):
        label = f"{type(link).__name__}[{index}]"
        surfaces[f"str() of {label}"] = str(link)
        surfaces[f"repr() of {label}"] = repr(link)
        errors = getattr(link, "errors", None)
        if callable(errors):
            surfaces[f"errors() of {label}"] = json.dumps(errors(), default=str)
    return surfaces


def configure_provider(
    monkeypatch: pytest.MonkeyPatch,
    base_url: str,
    *,
    with_key: bool = True,
    environment: str | None = None,
    variable: str = AI_PROVIDER_BASE_URL_VARIABLE,
) -> None:
    """Point a provider at `base_url`, with or without a key, in a named environment.

    `environment` is optional and every test whose subject is one of the two
    environment-conditioned rules passes it (`docs/MISTAKES.md` entry 40). Left
    unset, the value is `.env.example`'s own, laid down by `configured_env` — which
    is right for the rules that do not read it, and is stated in the module
    docstring rather than repeated on each of them.

    `variable` is the real provider's base URL unless a caller says otherwise,
    because every transport and catalog rule in this module is a rule about the
    real triple. The one pair of tests whose subject is the mock's triple passes
    `MOCK_AI_PROVIDER_BASE_URL_VARIABLE`, and the key follows the real side either
    way: the mock's own key is not what makes a base URL legal or illegal, and
    setting it here would put a second variable into rules that are not about it.
    """
    name, info = real_key_field(load_settings_class())
    if environment is not None:
        monkeypatch.setenv(ENVIRONMENT_VARIABLE, environment)
    monkeypatch.setenv(variable, base_url)
    if with_key:
        monkeypatch.setenv(variable_for(name, info), FAKE_PROVIDER_CREDENTIAL)
    else:
        monkeypatch.delenv(variable_for(name, info), raising=False)


@pytest.mark.parametrize("with_key", (True, False), ids=("key set", "no key set"))
@pytest.mark.parametrize("environment", ("development", *DEPLOYMENT_ENVIRONMENTS))
def test_an_https_provider_url_is_accepted_wherever_it_points(
    configured_env: dict[str, str],
    deployed_identity_provider: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    with_key: bool,
    environment: str,
) -> None:
    """The ordinary deployment: a hosted provider over TLS, with a key or without one.

    **Run in a deployment as well as in development since E2-07**, which is the
    row that keeps that ticket's environment condition from being implemented as
    "a deployment refuses everything". The `development` row is spelled as a
    literal rather than read from `app.config`, because parametrisation needs a
    value at collection time and importing the application there would make a
    missing module a collection error rather than a red;
    `test_the_development_row_above_is_the_environment_app_config_names` holds
    that literal against the constant.

    The two deployment rows carry `deployed_identity_provider`, which also moves
    the AI provider off `.env.example`'s mock address — without it the refusal
    under test would be E0-39's or E2-07's own catalog rule firing on a background
    value.

    The permitted case, asserted first and separately, because a rule that refuses
    plain HTTP is trivially satisfiable by refusing everything — and a startup
    that turns away the configuration `.env.example` documents is a rule nobody
    can deploy behind.

    **The without-a-key row is E0-37 item 12's control**, and it is the half that
    keeps that item from being satisfied the lazy way. The rule stops consulting
    the key at all, so "refuse an unauthenticated provider" would pass every
    refusal case below while turning away a TLS-terminated model server in the
    cluster next door — which is the deployment the item explicitly leaves
    supported. What changes is the *scheme* required off this machine, and
    nothing else.
    """
    configure_provider(
        monkeypatch, OFF_MACHINE_HTTPS_URL, with_key=with_key, environment=environment
    )

    settings = load_settings_class()()

    assert settings is not None, (
        f"`Settings` refused {OFF_MACHINE_HTTPS_URL} under ENVIRONMENT={environment!r}, a hosted "
        f"provider reached over TLS {'with' if with_key else 'without'} a key configured. That is "
        "the deployment a real institution runs, and E0-37 item 12 requires the transport rule to "
        "read the scheme and the host rather than whether a credential is present."
    )


@pytest.mark.parametrize("with_key", (True, False), ids=("key set", "no key set"))
@pytest.mark.parametrize("base_url", LOOPBACK_HTTP_URLS)
@pytest.mark.parametrize("environment", ("development", *DEPLOYMENT_ENVIRONMENTS))
def test_a_plain_http_provider_url_is_accepted_on_this_machine(
    configured_env: dict[str, str],
    deployed_identity_provider: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    base_url: str,
    with_key: bool,
    environment: str,
) -> None:
    """Plain HTTP to this machine stays legal, in all three spellings of it.

    §7.4's whole provider argument is that the endpoint may be "a hosted provider,
    a proxy, or a local server such as vLLM or Ollama", and the local server is
    reached over plain HTTP on the loopback interface, where there is no network
    to read a key off. A transport rule that refuses it refuses the cheapest way
    to run this project without a hosted provider at all — the thing E0-13's
    definition of done asks `README.md` to explain.

    Three spellings rather than one, because they are three separate ways to write
    the same permission and a rule written against any one of them turns the other
    two away. `[::1]` in particular is what a machine with IPv6 first resolves
    `localhost` to.

    **With a key and without one**, since E0-37 item 12: the rule no longer reads
    the key, and a local Ollama is the deployment least likely to have one. A fix
    that refused every keyless provider would take this row down with it, which is
    the near miss that separates "off this machine means https" from "a provider
    must be authenticated".

    **In every environment, since E2-07.** That ticket makes the transport rule
    environment-conditioned, and the exemption for this machine is not the part
    that moves: a model server in the same pod is reached at `localhost` by a
    production container as readily as by a laptop, and there is no wire either
    way. These rows are what stop the condition being written as "in a deployment,
    require https" — which refuses the sidecar deployment ADR 0056's consequences
    already name as supported.
    """
    configure_provider(monkeypatch, base_url, with_key=with_key, environment=environment)

    settings = load_settings_class()()

    assert settings is not None, (
        f"`Settings` refused {base_url} under ENVIRONMENT={environment!r}, which is plain HTTP to "
        f"this machine, {'with' if with_key else 'without'} a key configured. There is no network "
        "between the process and a local model server, so there is nothing for the transport rule "
        "to protect — and refusing it makes running without a hosted provider impossible."
    )


@pytest.mark.parametrize("with_key", (True, False), ids=("key set", "no key set"))
@pytest.mark.parametrize("environment", DEPLOYMENT_ENVIRONMENTS)
def test_a_plain_http_provider_url_to_another_host_is_refused_in_a_deployment(
    configured_env: dict[str, str],
    deployed_identity_provider: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    with_key: bool,
    environment: str,
) -> None:
    """Cleartext to a model on another host is refused at startup, key or no key.

    The two things travelling over that connection are the provider key in a
    header and the student's comment in the body. SPEC §10 keeps secrets in the
    environment or the secret store, and §4 keeps a comment to the surfaces it
    names; plain HTTP to another host puts both on the wire for anything between
    here and there.

    **The no-key row is E0-37 item 12 and was legal until it.** The rule used to
    return early when no key was configured, so `http://vllm.internal/v1` with no
    credential met no check at all — offered as a supported deployment in
    `README.md`, in `.env.example` and in the validator's own docstring. The key
    is only one of the two secrets on that link and it is the less serious one:
    every prompt the gateway sends carries the student's free-text comment, which
    §4 confines to named surfaces and §10 keeps off the wire in the clear. Todd
    decided it on 2026-08-18 — an encrypted transport whenever the model is on
    another host, with or without a credential.

    At startup rather than on first use, because the alternative fails in the
    §3.3 fail-open direction: a call that cannot be made is an outage, an outage
    floors, and the misconfiguration is invisible while participation credit is
    handed out on a character count.

    The *message* is not asserted here — the test below reads that from the
    surface an operator actually sees. The type is, and it is the whole assertion:
    an `assert refused.value is not None` after `pytest.raises` cannot fail, and
    this file has written one before (`docs/MISTAKES.md` entry 3, its
    twenty-fifth instance).

    **`ConfigurationError` rather than `Exception`**, and the reason is not the
    lint rule that noticed it. A bare `Exception` is satisfied by an
    `AttributeError` from `load_settings_class()` if `Settings` is renamed or
    moved — a broken test reading as a refused configuration, which is the exact
    inversion this suite is for. Measured on this path rather than assumed: an
    off-machine `http://` URL with a key set raises
    `app.config.ConfigurationError` out of `Settings()` directly.

    **Nothing here names the validator.** The function is renamed by the same
    item — it is no longer about credentialled endpoints — and a test that asserted
    the name would be red for the rename rather than for the rule. The controls
    that keep this from being satisfied by a rule that refuses everything are the
    two acceptance tests above, both of which now run without a key too.

    **The environment is stated, and the test is renamed for it, by E2-07.** That
    ticket makes this rule apply outside development only, so the same
    configuration is *accepted* on a developer's machine — which is the test
    below. Before that change this ran under `.env.example`'s `development` and
    passed because the rule was unconditional; afterwards it would have been red
    against a correct implementation, which is `docs/MISTAKES.md` entry 22's
    shape: a new rule making an earlier ticket's test fail, with the repair on the
    other side of the test wall from whoever meets it.
    """
    configure_provider(
        monkeypatch, OFF_MACHINE_HTTP_URL, with_key=with_key, environment=environment
    )

    with pytest.raises(load_configuration_error()):
        load_settings_class()()


def test_a_plain_http_provider_url_to_another_host_is_accepted_in_development(
    configured_env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The pair to the test above, and the reason E2-07 could change that rule at all.

    The development stack's own provider is `http://mock-ai:8000/v1` — cleartext,
    to a Compose service name, which is not this machine by any reading. The rule
    as E0-37 left it refuses that value unconditionally, so E2-07's first and
    fourth acceptance criteria are unsatisfiable without this exemption existing.

    **The exemption is the environment and not the host.** ADR 0077 already draws
    that line for the identity provider's four URLs, and this rule is written to
    match it rather than to carve out the one address the development stack uses:
    a developer running a model server on another machine on their own network is
    the same situation, and a rule that named only `mock-ai` would still refuse
    them while being one line longer.

    **The mutation this kills:** the transport rule left unconditional, which is
    the state at HEAD and which makes `docker compose up` from a clean checkout
    fail to start the API. **The near miss that must stay red:** the identical URL
    in a deployment, which is the test above.
    """
    configure_provider(
        monkeypatch, OFF_MACHINE_HTTP_URL, with_key=False, environment=development_environment()
    )

    settings = load_settings_class()()

    assert settings is not None, (
        f"`Settings` refused {OFF_MACHINE_HTTP_URL} in development. E2-07 points `.env.example` "
        "at `http://mock-ai:8000/v1`, which is cleartext to a host that is not this machine, so "
        "an unconditional transport rule stops the development stack from starting at all — and "
        "with it every e2e run, which copies that file to `.env`."
    )


@pytest.mark.parametrize("with_key", (True, False), ids=("key set", "no key set"))
@pytest.mark.parametrize("shape", list(USERINFO_URLS))
@pytest.mark.parametrize("environment", ("development", *DEPLOYMENT_ENVIRONMENTS))
def test_a_provider_url_carrying_a_credential_is_refused(
    configured_env: dict[str, str],
    deployed_identity_provider: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    shape: str,
    with_key: bool,
    environment: str,
) -> None:
    """A credential in the URL is refused outright — over TLS, on this machine, key or no key.

    The defect this is written against was the *condition* rather than the check:
    the transport rule ran only when the key variable was set, so a URL that
    carried its credential instead of setting that variable was never examined.
    httpx turns userinfo into a real `Authorization: Basic` header, so the
    credential went on the wire, was captured at the receiving server, and — the
    field being a plain `str` — rendered in `repr(settings)` and `model_dump()` on
    the way past.

    **Both parametrisations are the point.** Without a key set is the case the old
    rule missed entirely; over https and on loopback are the cases a narrower fix
    would have left legal. The last two shapes are the ones a rule written around
    a `user:password@` pattern misses: a username with no password at all, and a
    username with an empty one.

    The control that this is a rule about userinfo rather than a rule that refuses
    everything is `test_an_https_provider_url_is_accepted_wherever_it_points` and
    `test_a_plain_http_provider_url_is_accepted_on_this_machine` — the same URLs
    without a credential in them, required to build.

    The type is named for the reason given on the test above: a bare `Exception`
    is satisfied by an `AttributeError` from a moved symbol, and eight
    parametrisations all passing on one would read as a rule holding everywhere.

    **The environment rows are E2-07's, and they say what did *not* change.** That
    ticket makes the transport rule conditional; this one stays unconditional,
    because a credential belongs in the URL in no environment — the field is a
    plain displayable `str` that §6.3's admin view renders, on a laptop as much as
    in production. Written as a parametrisation rather than as prose so that a
    condition added to the wrong validator is a red rather than a paragraph
    somebody has to notice is now false.
    """
    configure_provider(
        monkeypatch, USERINFO_URLS[shape], with_key=with_key, environment=environment
    )

    with pytest.raises(load_configuration_error()):
        load_settings_class()()


def test_the_refusal_of_a_url_carrying_a_credential_quotes_neither_it_nor_the_host(
    configured_env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The refusal has to be readable without repeating what it refused.

    Same shape and same reason as the insecure-transport refusal below it, and a
    sharper case: what is being refused *is* a credential, so a diagnostic that
    quotes the URL back publishes the thing the rule exists to keep out of every
    other surface. A startup error goes to the container log and into whatever the
    operator pastes when asking for help.

    Control first: an unrelated refusal, with none of these three values
    configured, has to contain no fragment of any of them. That is what says the
    username, the password and the host do not collide with the report's own
    vocabulary, so the silence asserted afterwards means something rather than
    nothing (`docs/MISTAKES.md` entry 3).

    **Development, stated** (`docs/MISTAKES.md` entry 40). The rule under test is
    the unconditional one, so the environment is not the subject — but the
    *control* builds the whole application under `.env.example`'s values, and
    since E2-07 those include a provider address a deployment refuses. Left to
    whatever the environment happened to be, the control would refuse for the
    right reason today and for the wrong one after one edit.
    """
    monkeypatch.setenv(ENVIRONMENT_VARIABLE, development_environment())
    restored = configured_env.get(REQUIRED_DEPLOYMENT_VARIABLE)
    assert restored is not None, (
        f"`.env.example` documents no {REQUIRED_DEPLOYMENT_VARIABLE}, so the control below cannot "
        "put the configuration back before the assertion that matters runs."
    )
    needles = {
        "the username": USERINFO_USER,
        "the password": USERINFO_CREDENTIAL,
        "the host": OFF_MACHINE_HOST,
    }

    monkeypatch.delenv(REQUIRED_DEPLOYMENT_VARIABLE, raising=False)
    with pytest.raises(load_configuration_error()) as unrelated:
        build_app()

    control = renderings_of(unrelated.value)
    collisions = {
        f"{label} in {where}": leaked_fragments(rendering, needle)
        for label, needle in needles.items()
        for where, rendering in control.items()
        if leaked_fragments(rendering, needle)
    }
    assert not collisions, (
        f"These needles share fragments with a startup refusal none of them was configured in: "
        f"{collisions}. The assertions below would then report ordinary words as a leaked "
        "credential. The repair is the needle in this file, not the threshold."
    )

    monkeypatch.setenv(REQUIRED_DEPLOYMENT_VARIABLE, restored)
    configure_provider(monkeypatch, USERINFO_URLS["https, off machine"], with_key=False)
    with pytest.raises(load_configuration_error()) as refused:
        build_app()

    surfaces = renderings_of(refused.value)
    variable = AI_PROVIDER_BASE_URL_VARIABLE.lower()

    assert any(variable in rendering.lower() for rendering in surfaces.values()), (
        f"The refusal of a URL carrying a credential never names "
        f"{AI_PROVIDER_BASE_URL_VARIABLE} — the renderings were {surfaces}. An operator meets "
        "this in a container log with no traceback into the validator, and a diagnostic that does "
        "not say which variable is wrong sends them to change whichever one makes it stop."
    )

    for label, needle in needles.items():
        leaked = {
            where: leaked_fragments(rendering, needle)
            for where, rendering in surfaces.items()
            if leaked_fragments(rendering, needle)
        }
        assert not leaked, (
            f"The startup refusal quotes {label}: {leaked}. The renderings were {surfaces}. What "
            "this rule refuses is a credential, so a diagnostic that repeats the URL puts it in "
            "the container log — the one place §10 exists to keep it out of. Naming the variable "
            "is what the message is for."
        )


def test_the_refusal_of_an_insecure_provider_url_names_the_variable_and_quotes_nothing_else(
    configured_env: dict[str, str],
    deployed_identity_provider: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """What the operator is told: which variable, and neither the URL nor the key.

    **Asserted through `create_app()` rather than through the validator**, because
    a validator's own message does not reach the operator. The startup report is
    assembled from the field name, the field's static `description` and pydantic's
    error code, so a `value_error` renders as a generic sentence however carefully
    it was worded — the implementer put the rule in the field's `description` for
    that reason, and widening the report to interpolate a validator's message
    would mean trusting every future validator not to quote its own input, which
    is `docs/MISTAKES.md` entry 2's shape pointed at a credential.

    Three things, and the order is the point. The control runs first: an unrelated
    refusal, with this test's host configured nowhere, must contain no fragment of
    it — that is what says the host token does not collide with the report's own
    vocabulary, so the silence asserted afterwards means something. Then the
    refusal has to name `AI_PROVIDER_BASE_URL`, since an operator who cannot tell
    which variable is wrong will reach for the one thing that makes the message go
    away. And then it must quote neither the URL it refused nor the key that made
    it refuse: a startup diagnostic is printed to the container log and pasted
    into chat windows, which is exactly where a `.env` line does not belong.

    **A deployment's environment, since E2-07**, because the rule this reads the
    message of applies only outside development now. `deployed_identity_provider`
    moves the identity provider and the AI provider off `.env.example`'s mock
    addresses first, so the refusal asserted here is this rule's rather than a
    neighbour's — with them left in place, the message would name whichever
    variable the report happened to reach first.
    """
    monkeypatch.setenv(ENVIRONMENT_VARIABLE, DEPLOYMENT_ENVIRONMENTS[0])
    restored = configured_env.get(REQUIRED_DEPLOYMENT_VARIABLE)
    assert restored is not None, (
        f"`.env.example` documents no {REQUIRED_DEPLOYMENT_VARIABLE}, so the control below cannot "
        "put the configuration back before the assertion that matters runs."
    )

    monkeypatch.delenv(REQUIRED_DEPLOYMENT_VARIABLE, raising=False)
    with pytest.raises(load_configuration_error()) as unrelated:
        build_app()

    control = renderings_of(unrelated.value)
    collisions = {
        where: leaked_fragments(rendering, OFF_MACHINE_HOST)
        for where, rendering in control.items()
        if leaked_fragments(rendering, OFF_MACHINE_HOST)
    }
    assert not collisions, (
        f"`OFF_MACHINE_HOST` shares {collisions} with a startup refusal it was configured nowhere "
        "in, so the assertion below would report an ordinary word as a leaked URL. The repair is "
        "the host token in this file, not the threshold."
    )

    # Restored by name rather than with `monkeypatch.undo()`, which would also
    # undo `configured_env` — the whole documented environment and the working
    # directory it moved out of the repository — and leave the refusal below
    # firing on the wrong variable.
    monkeypatch.setenv(REQUIRED_DEPLOYMENT_VARIABLE, restored)
    configure_provider(monkeypatch, OFF_MACHINE_HTTP_URL)
    with pytest.raises(load_configuration_error()) as refused:
        build_app()

    surfaces = renderings_of(refused.value)
    variable = AI_PROVIDER_BASE_URL_VARIABLE.lower()

    assert any(variable in rendering.lower() for rendering in surfaces.values()), (
        f"The refusal of an insecure provider URL never names {AI_PROVIDER_BASE_URL_VARIABLE} — "
        f"the renderings were {surfaces}. An operator meets this in a container log with no "
        "traceback into the validator, and a diagnostic that does not say which variable is wrong "
        "sends them to change whichever one makes it stop."
    )

    for label, secret in (
        ("the URL it refused", OFF_MACHINE_HOST),
        ("the provider key", FAKE_PROVIDER_CREDENTIAL),
    ):
        leaked = {
            where: leaked_fragments(rendering, secret)
            for where, rendering in surfaces.items()
            if leaked_fragments(rendering, secret)
        }
        assert not leaked, (
            f"The startup refusal quotes {label}: {leaked}. The renderings were {surfaces}. SPEC "
            "§10 keeps secrets in the environment or the secret store, and a startup diagnostic "
            "goes to the container log and into whatever the operator pastes when asking for "
            "help. Naming the variable is what the message is for; repeating its value is not."
        )


# ---------------------------------------------------------------------------
# The mock provider's own name — ticket E2-07.
#
# The stack now starts a service that answers chat completions, in the base
# Compose file, in every deployment (ADR 0038). ADR 0077 found what that means for
# the identity provider and the argument transfers exactly: a deployment that sets
# no `AI_PROVIDER_BASE_URL` — or copies the development one forward — ships every
# student comment to a container in its own network and stores whatever it
# answers as a classification, with nothing to say the model was never asked. The
# ticket puts it plainly: "nothing may point production at it".
#
# Every refusal below carries `https`, so that only the catalog can be what
# refuses it: the development stack's own address is cleartext, and a cleartext
# mock address is refused by the transport rule as well.
# ---------------------------------------------------------------------------


def test_the_development_environment_this_module_parametrises_over_is_the_one_app_config_names(
    configured_env: dict[str, str],
) -> None:
    """A control on the `"development"` literal in the parametrisations above.

    **A red here means these tests are broken, not the code.** Parametrisation
    needs its values at collection time, and importing `app.config` there would
    turn a missing module into a collection error rather than a red — so the rows
    above spell the development environment as a literal, and this is what holds
    it against `app.config.DEVELOPMENT_ENVIRONMENT`, which E0-37 item 2 makes its
    one definition site.

    Without it, a renamed constant would leave every "accepted in development" row
    above running under a *deployment* name and passing only because the value
    they set is legal in both — and the two rows that are legal in one environment
    only would fail for a reason no message would explain.
    """
    assert development_environment() == "development", (
        f"`app.config.DEVELOPMENT_ENVIRONMENT` is {development_environment()!r} and the "
        "parametrisations in this module spell 'development'. They have to be the same string, or "
        "half the rows above are running in an environment nobody chose."
    )


@pytest.mark.parametrize("environment", DEPLOYMENT_ENVIRONMENTS)
def test_a_blank_provider_base_url_is_refused_in_a_deployment(
    configured_env: dict[str, str],
    deployed_identity_provider: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    environment: str,
) -> None:
    """E2-12's security review: a deployment that forgot the AI block stops instead of guessing.

    `.env.example` shipped `AI_PROVIDER_BASE_URL` carrying a working public
    endpoint. Beside a blank `AI_PROVIDER_API_KEY` — blank for a good reason, since
    no credential may be committed — that produced the quietest failure in this
    ticket: a deployment configures the database, the broker, the session secret
    and the identity provider, leaves the AI block alone because it looks
    configured already, and starts cleanly. Every §3.3 validation then posts a
    student's comment to a third party under a placeholder bearer token. Nothing
    raises, nothing warns, and SPEC §10's rule about PII in logs says nothing about
    a request body.

    The field is required with no default, so the fix is to ship the line blank:
    the process refuses at startup and names the variable, which is what a
    forgotten required setting is supposed to do. The endpoint moves into the
    comment beside the entry, where an operator copies it on purpose.

    **This is the deployment half of a pair.** The other half is below: in
    development the same blank must be *accepted*, because the development stack
    reads the mock triple and SPEC §14.3 requires a clean checkout to come up. A
    rule that refused everywhere would take `docker compose up` down; one that
    refused nowhere is the finding.

    **The mutation this kills:** giving the field a default, or leaving the blank
    acceptable in a deployment. **The near miss that must stay green:** any real
    endpoint on that line in a deployment, which
    `test_an_https_provider_url_is_accepted_wherever_it_points` already holds.
    """
    configure_provider(monkeypatch, "", with_key=True, environment=environment)

    with pytest.raises(load_configuration_error()):
        load_settings_class()()


def test_a_blank_provider_base_url_is_accepted_in_development(
    configured_env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The development half: a clean checkout comes up with no real provider configured.

    SPEC §14.3 requires `docker compose up` on a fresh clone to reach a launchable
    system, and CI's e2e job runs `cp .env.example .env` verbatim. A development
    stack classifies through the mock triple, so it needs no real endpoint at all —
    and after E2-12's security review the documented real endpoint is blank.
    Refusing it here would mean the file this repository ships cannot start the
    stack this repository ships.

    **Pairing this with the deployment rows above is what makes either mean
    anything.** A rule that refused a blank everywhere passes those and breaks the
    clean checkout; a rule that accepted one everywhere passes this and is the
    security finding. The line is the environment, and both sides of it are
    asserted.

    The refusal does not disappear in development, it moves. A gateway built
    `live=True` still needs the real endpoint, and
    `tests/unit/test_the_gateway_reads_the_provider_triple_the_flag_selects.py`
    holds that; the eval runner is the only caller that asks for one.

    **The mutation this kills:** making the requirement unconditional, which stops
    a clean checkout starting. **The near miss that must stay red:** the same blank
    in a deployment, immediately above.
    """
    configure_provider(monkeypatch, "", with_key=False, environment=development_environment())

    settings = load_settings_class()()

    assert settings is not None, (
        "`Settings` refused a blank `AI_PROVIDER_BASE_URL` in development. That is what "
        "`.env.example` documents after E2-12's security review, and CI's e2e job copies "
        "that file unedited — so refusing it means `docker compose up` on a clean checkout "
        "does not start the API, which is SPEC §14.3's exit criterion for every epic.\n"
        "\n"
        "Nothing in development reads the real triple: `AIGateway(live=False)` takes the "
        "mock's. The one caller that needs a real endpoint asks for it explicitly, and that "
        "is where the refusal belongs."
    )


def test_the_development_stack_may_point_the_mock_triple_at_the_mock(
    configured_env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """E2-07 acceptance criterion 1's configuration half: `.env.example`'s value builds.

    `http://mock-ai:8000/v1` is what `.env.example` documents and what CI's e2e job
    copies to `.env`, and a red here means `docker compose up` from a clean
    checkout does not start the API — SPEC §14.3's exit criterion for every epic.
    That guarantee is exactly what it was; what changed on 2026-09-02 is which
    variable holds the address. The configuration split moved it to
    `MOCK_AI_PROVIDER_BASE_URL`, so this test asks the question of that variable.

    **It is now half of a pair, and the other half is the test below.** The
    address is legal *here* and illegal on the real triple in every environment,
    and those two together are what the split buys: the development stack still
    classifies, and nothing that reaches a paid provider can be pointed at a
    character counter.

    **The mutation this kills:** applying the catalog rule to the mock's own base
    URL, which refuses the development stack and passes every refusal test in this
    module. **The near miss that must stay red:** the identical URL on
    `AI_PROVIDER_BASE_URL`, immediately below.
    """
    configure_provider(
        monkeypatch,
        DEVELOPMENT_MOCK_AI_URL,
        with_key=False,
        environment=development_environment(),
        variable=MOCK_AI_PROVIDER_BASE_URL_VARIABLE,
    )

    settings = load_settings_class()()

    assert settings is not None, (
        f"`Settings` refused {DEVELOPMENT_MOCK_AI_URL} on "
        f"{MOCK_AI_PROVIDER_BASE_URL_VARIABLE} in development. That is the address "
        "`.env.example` documents, the address CI's e2e job runs the stack with, and the only "
        "provider a development machine has — refusing it leaves the stack unable to start."
    )


def test_the_mock_triple_may_still_name_the_mock_in_a_deployment(
    configured_env: dict[str, str],
    deployed_identity_provider: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Nothing outside development reads the mock's triple, so its value is no rule's business.

    The configuration split settles selection: `AIGateway(live=False)` reads the
    mock triple in development and test, and the real triple in a deployment;
    `live=True` reads the real triple always. So in a deployment nothing consults
    `MOCK_AI_PROVIDER_BASE_URL` at all, and refusing its value there would refuse a
    variable the process is not going to look at — including on every deployment
    that simply copied `.env.example` forward, which is the ordinary case.

    **This is the permissive half of a pair and it is worth nothing alone.** The
    strict half is the test below: the *real* base URL naming `mock-ai` is refused
    in every environment. A rule that refused both would take the development stack
    down; a rule that refused neither would leave a deployment classifying against
    a character counter. What this file can see is that the rules attach to the
    real triple and not to the mock's.

    **What this cannot see, and where it is seen.** That a deployment's gateway
    *actually reads* the real triple is a property of `AIGateway`, not of
    `Settings`, and nothing in this module builds one.
    `tests/unit/test_the_gateway_reads_the_provider_triple_the_flag_selects.py
    ::test_a_gateway_that_is_not_live_reads_the_real_triple_in_a_deployment` is
    that assertion, and the two are not substitutes: this one would pass over a
    gateway that read the mock triple happily, and that one would pass over a
    `Settings` that refused every deployment at startup.

    **The mutation this kills:** applying the catalog rule to every base-URL
    setting rather than to the real one, which passes the refusal tests below and
    stops a deployment starting from an unedited `.env.example`.
    """
    configure_provider(
        monkeypatch,
        DEVELOPMENT_MOCK_AI_URL,
        with_key=False,
        environment=DEPLOYMENT_ENVIRONMENTS[0],
        variable=MOCK_AI_PROVIDER_BASE_URL_VARIABLE,
    )

    settings = load_settings_class()()

    assert settings is not None, (
        f"`Settings` refused {DEVELOPMENT_MOCK_AI_URL} on "
        f"{MOCK_AI_PROVIDER_BASE_URL_VARIABLE} in {DEPLOYMENT_ENVIRONMENTS[0]!r}. Nothing outside "
        "development and test reads that triple, so its value is not what stops a deployment "
        "reaching the mock — the rule on the real base URL is, and it is asserted below. "
        "Refusing this one stops a deployment that copied `.env.example` forward from starting "
        "at all."
    )


def test_the_real_provider_may_not_be_pointed_at_the_mock_even_in_development(
    configured_env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The catalog rule got stricter on 2026-09-02, and this is the environment it gained.

    It used to be conditioned on the environment, and the exemption had one job:
    `.env.example` had a single provider base URL, it pointed at the mock, and a
    development stack had to be able to start. That address now lives on
    `MOCK_AI_PROVIDER_BASE_URL` — asserted immediately above — so the exemption
    protects nothing and costs something real.

    What it costs is the eval gate. `tests/evals/runner.py` builds its gateway
    `live=True`, which reads the real triple *in every environment including a
    developer's machine*, so a `mock-ai` address there makes `make evals` measure
    E2-07's twenty-five-character rule and write the score down as SPEC §9.3's
    precision and recall floor. The run succeeds, the numbers look plausible, and
    nothing says the model was never asked.

    **The pair, and neither half means much alone:** the mock's own triple accepts
    this address in development (above), and the real triple refuses it there
    (here). One line crossed, both directions asserted.

    **The mutation this kills:** leaving the environment condition on the catalog
    rule when the split moved the address out from under it — which passes every
    other test in this module, since every other row that exercises the rule is
    already in a deployment. **The near miss that must stay green:**
    `NON_MOCK_AI_URL_SPELLINGS`, where the host merely contains the service name.
    """
    configure_provider(
        monkeypatch,
        MOCK_AI_URL_SPELLINGS["the development stack's address over TLS"],
        with_key=False,
        environment=development_environment(),
    )

    with pytest.raises(load_configuration_error()):
        load_settings_class()()


@pytest.mark.parametrize("environment", ("development", *DEPLOYMENT_ENVIRONMENTS))
@pytest.mark.parametrize("spelling", list(MOCK_AI_URL_SPELLINGS))
def test_a_url_addressing_the_mock_provider_is_refused_in_every_environment(
    configured_env: dict[str, str],
    deployed_identity_provider: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    spelling: str,
    environment: str,
) -> None:
    """A process whose real provider names the mock stops at startup, however the URL is spelled.

    **The environment row was added on 2026-09-02 and the rest is unchanged.** The
    rule was conditioned on the environment because `.env.example`'s single base
    URL pointed at the mock; the configuration split moved that address to
    `MOCK_AI_PROVIDER_BASE_URL`, so the exemption has nothing left to protect and
    the real triple refuses the mock everywhere. The reasoning, and the pair that
    makes the strengthening safe, are in
    `test_the_real_provider_may_not_be_pointed_at_the_mock_even_in_development`
    above; the four spellings below are why the rule is about the *host*.

    The ticket's security-relevant note: "nothing may point production at it." The
    base Compose file starts `mock-ai` in every deployment (ADR 0038), so this is
    not a hypothetical misconfiguration — it is the one that resolves, answers,
    and looks like a working classifier. What it produces is a `substantive` for
    every comment over 25 characters, stored with a real prompt version and model
    id against a student's participation.

    **Four spellings, because the rule is about the host.** A container on this
    network reaches the mock at `mock-ai` on whatever port it listens on, so a rule
    written against `http://mock-ai:8000/v1` — the exact string `.env.example`
    ships, and the obvious thing to compare — is defeated by an operator who
    copies the address and changes the port, or who puts TLS in front of it.

    **The mutation this kills:** no catalog rule at all, which is the state at
    HEAD; equality against the development stack's full URL; and a rule that reads
    `host:port` rather than the host.

    **Every row carries `https`**, so the transport rule cannot be what refuses
    it: the cleartext spellings are refused by either rule and a green row nobody
    can attribute is `docs/MISTAKES.md` entry 3.
    """
    configure_provider(
        monkeypatch,
        MOCK_AI_URL_SPELLINGS[spelling],
        with_key=False,
        environment=environment,
    )

    with pytest.raises(load_configuration_error()):
        load_settings_class()()


def test_the_mock_provider_host_is_refused_whatever_case_it_is_written_in(
    configured_env: dict[str, str],
    deployed_identity_provider: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`MOCK-AI` is the same host as `mock-ai`, so the refusal has to read it as one.

    Host names are case-insensitive (RFC 4343) and Compose folds nothing of its
    own, so `MOCK-AI` in a container reaches the mock exactly as the lower-case
    spelling does. This is a judgement rather than a transcription of the ticket,
    and it is a narrow one — the ticket's rule is about the URL's host, and this is
    that host.

    **The mutation this kills:** `url.netloc.split(":")[0] == "mock-ai"`, which
    does not fold case, as against `urlsplit(url).hostname`, which does.

    Written as its own test rather than as a fifth spelling above, exactly as
    `tests/unit/test_oidc_provider_configuration.py` does, so that a dispute about
    the reading costs one test rather than four.
    """
    configure_provider(
        monkeypatch,
        f"https://{MOCK_AI_SERVICE.upper()}:8000/v1",
        with_key=False,
        environment=DEPLOYMENT_ENVIRONMENTS[0],
    )

    with pytest.raises(load_configuration_error()):
        load_settings_class()()


@pytest.mark.parametrize("spelling", list(NON_MOCK_AI_URL_SPELLINGS))
def test_a_url_that_merely_contains_the_mock_providers_name_is_accepted_in_a_deployment(
    configured_env: dict[str, str],
    deployed_identity_provider: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    spelling: str,
) -> None:
    """The host is compared as a component, not searched for as a substring.

    Each row is an address a real institution could hold, and each is refused by
    the one-line version of this rule — `"mock-ai" in url` — which is the obvious
    way to write it and which the refusals above cannot tell from the right one. A
    subdomain, a host the name prefixes, a host the name ends, and a path segment:
    none of them resolves to the Compose service, which is the only thing the
    catalog names.

    **The mutation this kills:** substring matching, over the URL or over the host.
    **The near miss on the other side:** `MOCK_AI_URL_SPELLINGS` above, where the
    host is exactly the service name and every one is refused.
    """
    configure_provider(
        monkeypatch,
        NON_MOCK_AI_URL_SPELLINGS[spelling],
        with_key=False,
        environment=DEPLOYMENT_ENVIRONMENTS[0],
    )

    settings = load_settings_class()()

    assert settings is not None, (
        f"`Settings` refused {NON_MOCK_AI_URL_SPELLINGS[spelling]!r}, whose host is not "
        f"{MOCK_AI_SERVICE!r}. The catalog is the Compose service name — the name by which a "
        "container on this stack reaches the mock — and nothing else resolves to it."
    )


def test_the_refusal_of_a_mock_provider_url_names_the_variable(
    configured_env: dict[str, str],
    deployed_identity_provider: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """What the operator reads: which setting is wrong.

    An operator meets this in a container log with no traceback into the
    validator, and this deployment has two provider settings that could carry a
    mock's name — the identity provider's five and this one. A refusal that says
    only "a mock address is configured" sends them to read six variables.

    Nothing else about the wording is pinned. The host may appear: it is what is
    being refused, and unlike the userinfo case there is no credential in it.

    **The mutation this kills:** a refusal raised on the right field with a
    message assembled from another one — which
    `tests/unit/test_oidc_provider_configuration.py` records as reachable, since
    `_describe_invalid_settings` builds what the operator reads out of the field
    name rather than out of the validator's own words.
    """
    configure_provider(
        monkeypatch,
        MOCK_AI_URL_SPELLINGS["another port"],
        with_key=False,
        environment=DEPLOYMENT_ENVIRONMENTS[0],
    )

    with pytest.raises(load_configuration_error()) as refusal:
        build_app()

    message = str(refusal.value)
    assert AI_PROVIDER_BASE_URL_VARIABLE.lower() in message.lower(), (
        f"The refusal does not name {AI_PROVIDER_BASE_URL_VARIABLE}: {message!r}. Six settings in "
        "this deployment can carry a mock's address, and the operator reading a container log has "
        "to learn which one did."
    )


def test_the_refused_provider_host_is_the_compose_service_name_the_mock_runs_as(
    mock_ai_service: str,
) -> None:
    """A control: the host this module refuses is the name the service actually runs under.

    **A red here means these tests are broken, or the mock has been renamed.** The
    catalog is written out above rather than derived, which is the right call for
    a one-entry rule that a reviewed diff should have to change — but a written-out
    catalog goes stale without anything failing, because a rule that refuses a name
    nothing runs under reports every configuration clean (`docs/MISTAKES.md` entry
    35, whose rule is that a guard which only ever reports absence has to be seen
    finding the thing on a subject that certainly has it).

    `mock_ai_service` is `tests/fixtures/mock_ai.py`'s single answer to "what is
    the mock provider called", and
    `tests/unit/test_mock_ai_service.py::test_the_base_compose_file_builds_the_mock
    _ai_service_from_this_repository` is what holds *that* against the Compose file
    — so the chain from this literal to a running container is closed rather than
    ending in a second literal.
    """
    assert mock_ai_service == MOCK_AI_SERVICE, (
        f"This module refuses the host {MOCK_AI_SERVICE!r} and the mock provider runs as the "
        f"Compose service {mock_ai_service!r}. Every refusal above is then about a name nothing on "
        "this stack answers to, and would pass against a deployment configured with the real one."
    )


def test_no_workflow_references_a_repository_secret_beyond_the_permitted_set() -> None:
    """Criterion 7: no `secrets.*` reference was added to a workflow without prior agreement.

    `CLAUDE.md` is unambiguous and this is the ticket that has a reason to break
    it: "Never add a secret reference to a workflow without asking first — a new
    `secrets.*` expression, a new environment binding, or widening an existing
    one. Ask, then wait for an answer; do not add it provisionally." The pull it
    resists is real — `ci.yml` already carries a notice saying that running the
    eval suite "needs a provider API key as a repository secret and a `secrets.*`
    reference in this workflow", and says it is "proposed, not wired".

    **This test passes on a correct tree today**, which is the point of it: it is
    a guard rather than a red assertion, and E0-13 is the first ticket that could
    trip it. `docs/MISTAKES.md` entry 2 — a rule stated in a document and asserted
    by nothing is a convention, and the next person to add one does so with every
    gate green.

    The canary is why the emptiness this reports can be believed: a regex that
    matches nothing and a workflow directory that was never read are the same
    silence, and only a string certainly present in the files tells them apart.
    """
    assert WORKFLOWS_DIR.is_dir(), f"{WORKFLOWS_DIR} does not exist, so nothing was searched."

    workflows = sorted(path for path in WORKFLOWS_DIR.iterdir() if path.suffix in {".yml", ".yaml"})
    assert workflows, f"{WORKFLOWS_DIR} holds no workflow files, so this test searched nothing."

    texts = {path: path.read_text(encoding="utf-8") for path in workflows}
    assert any(WORKFLOW_CANARY in text for text in texts.values()), (
        f"No file under {WORKFLOWS_DIR} contains {WORKFLOW_CANARY!r}, so either these are not "
        "GitHub Actions workflows or nothing was read. The search below reports the same "
        "emptiness for a directory it never opened as for one that is clean."
    )

    referenced = {
        f"{path.name}: {match}"
        for path, text in texts.items()
        for match in SECRET_REFERENCE.findall(text)
        if match not in PERMITTED_WORKFLOW_SECRETS
    }

    assert not referenced, (
        f"These workflows reference repository secrets outside the permitted set "
        f"{sorted(PERMITTED_WORKFLOW_SECRETS)}: {sorted(referenced)}. E0-13's seventh acceptance "
        "criterion: 'No `secrets.*` reference was added to a workflow without prior agreement.' "
        "CLAUDE.md: ask, wait for an answer, and do not add it provisionally. If one has been "
        "agreed, it is added to `PERMITTED_WORKFLOW_SECRETS` in this file in the same pull "
        "request, with the agreement quoted in the body."
    )


def test_the_secret_reference_pattern_matches_a_reference_and_not_a_mention() -> None:
    """The pattern above, run against what it must catch and what it must allow.

    Not a test of the ticket — a test of the search the test above depends on.
    `docs/MISTAKES.md` entry 3's rule for a pattern searched against a file: run
    it against the text you claim it catches *and* the text you claim it allows,
    because a pattern that has gone blind reports exactly what a clean workflow
    reports. The third case in that entry is a regex written with a plain space
    where the file held a newline, which went green against the exact comment it
    existed to catch.

    The allowed sample is the sentence `ci.yml` carries today: prose naming a
    `secrets.*` reference as something *not* wired. A pattern that matched it
    would fail this suite on a workflow that does exactly what the policy asks.
    """
    caught = SECRET_REFERENCE.findall("value: ${{ secrets.AI_PROVIDER_API_KEY }}")
    spaced = SECRET_REFERENCE.findall("value: ${{secrets.OTHER_KEY}}")
    prose = SECRET_REFERENCE.findall(
        "echo '::notice::Running the eval suite needs a provider API key as a repository secret "
        "and a secrets.* reference in this workflow.'"
    )

    assert caught == ["AI_PROVIDER_API_KEY"], (
        f"The pattern read a plain secret reference as {caught}. Every assertion in the test "
        "above is downstream of it."
    )
    assert spaced == ["OTHER_KEY"], (
        f"The pattern read an unspaced `${{{{secrets.NAME}}}}` as {spaced}. Both spacings are "
        "legal in a workflow and only one of them was being searched for."
    )
    assert prose == [], (
        f"The pattern matched prose that merely mentions `secrets.*` and read {prose} out of it. "
        "`ci.yml` carries exactly that sentence today, so this would fail against a repository "
        "that is following the policy."
    )


def test_every_workflow_parses_so_the_search_above_read_real_files() -> None:
    """The files searched are workflows rather than whatever happens to sit in the directory.

    A cheap second guard on the same emptiness: the canary says the text looks
    like Actions, and this says each file is YAML with jobs in it. A workflow that
    stopped parsing would still contain `${{`, still be searched by a regex, and
    still report no secrets — while GitHub ran nothing at all.
    """
    assert WORKFLOWS_DIR.is_dir(), f"{WORKFLOWS_DIR} does not exist, so nothing was read."

    workflows = sorted(path for path in WORKFLOWS_DIR.iterdir() if path.suffix in {".yml", ".yaml"})
    assert workflows, f"{WORKFLOWS_DIR} holds no workflow files, so nothing was parsed."

    unreadable = []
    for path in workflows:
        try:
            document = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as failure:
            unreadable.append((path.name, str(failure)))
            continue
        if not isinstance(document, dict) or "jobs" not in document:
            unreadable.append((path.name, "no `jobs` mapping"))

    assert not unreadable, (
        f"These files under {WORKFLOWS_DIR} are not workflows this test can vouch for: "
        f"{unreadable}."
    )
