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

**The transport rule arrived from a review**, and it is the other half of "the key
is a secret": a key masked in every log and then sent in clear over a network is
a key in the open. Plain HTTP stays legal to this machine, where a local model
server needs no TLS and there is no network to read anything off, and is refused
to any other host while a key is configured. The refusal is asserted **through
`create_app()`**, because a `Settings` validator's own message never reaches the
operator — the startup report is built from the field name, the field's static
`description` and pydantic's error code, so asserting on a message the validator
raises would be asserting on something nobody sees.

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
# ruff's S105 keeps flagging the real thing; `tests/conftest.py` made the same
# choice.
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
AI_PROVIDER_BASE_URL_VARIABLE = "AI_PROVIDER_BASE_URL"

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

# The repository secrets a workflow may reference today. `GITHUB_TOKEN` is
# supplied by Actions itself rather than configured, so it is not a stored secret
# in the sense CLAUDE.md's policy is about. Everything else is Todd's call, in
# advance and in writing.
PERMITTED_WORKFLOW_SECRETS = frozenset({"GITHUB_TOKEN"})

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


def documented_key_variables(documented_env: Mapping[str, str]) -> list[str]:
    """Every `.env.example` entry whose name reads as the AI provider key."""
    return sorted(
        name
        for name in documented_env
        if any(word in name.upper() for word in PROVIDER_KEY_WORDS)
        and any(word in name.upper() for word in PROVIDER_KEY_QUALIFIERS)
    )


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


def one_key_field(settings_cls: type) -> tuple[str, Any]:
    """The single provider-key field, or a failure naming the criterion."""
    fields = settings_key_fields(settings_cls)
    if len(fields) != 1:
        pytest.fail(
            f"`Settings` has {len(fields)} fields that read as the AI provider key "
            f"({sorted(fields)}); it declares {sorted(getattr(settings_cls, 'model_fields', {}))}. "
            "E0-13's scope: 'Provider configuration from `Settings`: base URL, model, and a "
            "masked key', and the epic README adds that '`.env.example` entry needs a `Settings` "
            "field resolving it before the sync test will accept it'. If the field is spelled "
            "with a word `PROVIDER_KEY_WORDS` in this file does not reach, that constant is the "
            "one line that changes."
        )
    return next(iter(fields.items()))


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
    """
    entries = documented_key_variables(documented_env)
    assert entries, (
        "`.env.example` documents no variable that reads as the AI provider key. E0-13's scope: "
        "'Provider configuration from `Settings`: base URL, model, and a masked key', and its "
        "definition of done: '`.env.example` gains the AI provider variables with placeholder "
        "values.' The file has been holding the place since E0-01 — 'the provider key is not "
        "read yet — the gateway and its masked key land in E0-13'."
    )
    assert len(entries) == 1, (
        f"`.env.example` documents {entries}, and this file cannot tell which is the provider "
        "key. One key, one entry: say in the pull request what the others are for."
    )

    name, info = one_key_field(load_settings_class())
    resolved = variable_for(name, info)

    assert resolved == entries[0], (
        f"`Settings.{name}` resolves {resolved!r}, and `.env.example` documents the provider key "
        f"as {entries[0]!r}. An entry no setting reads is an entry that documents nothing, and a "
        "field reading a variable the file does not document is configuration nobody can find "
        "(ADR 0008)."
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
    """
    settings_cls = load_settings_class()
    name, info = one_key_field(settings_cls)
    monkeypatch.setenv(variable_for(name, info), FAKE_PROVIDER_CREDENTIAL)

    settings = settings_cls()

    assert FAKE_PROVIDER_CREDENTIAL in revealed(getattr(settings, name)), (
        f"`settings.{name}` no longer carries the key it was configured with — it holds "
        f"{getattr(settings, name)!r}. Hiding a credential from serialisation must not hide it "
        "from the code that authenticates with it, or the gateway reaches no hosted provider at "
        "all."
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
    """
    settings_cls = load_settings_class()
    name, info = one_key_field(settings_cls)
    monkeypatch.setenv(variable_for(name, info), FAKE_PROVIDER_CREDENTIAL)

    settings = settings_cls()
    assert FAKE_PROVIDER_CREDENTIAL in revealed(getattr(settings, name)), (
        f"`settings.{name}` did not take the value this test configured, so the rendering below "
        "would contain no key whatever the masking does. That is a gap in this file — or the "
        f"field does not read {variable_for(name, info)!r} — rather than a leak that was avoided."
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
    """
    settings_cls = load_settings_class()
    name, info = one_key_field(settings_cls)
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
    """
    monkeypatch.delenv(REQUIRED_DEPLOYMENT_VARIABLE, raising=False)

    with pytest.raises(Exception) as refused:
        load_settings_class()()

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
    monkeypatch: pytest.MonkeyPatch, base_url: str, *, with_key: bool = True
) -> None:
    """Point the provider at `base_url`, with or without a key configured."""
    settings_cls = load_settings_class()
    name, info = one_key_field(settings_cls)
    monkeypatch.setenv(AI_PROVIDER_BASE_URL_VARIABLE, base_url)
    if with_key:
        monkeypatch.setenv(variable_for(name, info), FAKE_PROVIDER_CREDENTIAL)
    else:
        monkeypatch.delenv(variable_for(name, info), raising=False)


def test_an_https_provider_url_is_accepted_wherever_it_points(
    configured_env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The ordinary deployment: a hosted provider over TLS, with a key.

    The permitted case, asserted first and separately, because a rule that refuses
    plain HTTP is trivially satisfiable by refusing everything — and a startup
    that turns away the configuration `.env.example` documents is a rule nobody
    can deploy behind.
    """
    configure_provider(monkeypatch, OFF_MACHINE_HTTPS_URL)

    settings = load_settings_class()()

    assert settings is not None, (
        f"`Settings` refused {OFF_MACHINE_HTTPS_URL}, a hosted provider reached over TLS with a "
        "key configured. That is the deployment `.env.example` documents."
    )


@pytest.mark.parametrize("base_url", LOOPBACK_HTTP_URLS)
def test_a_plain_http_provider_url_is_accepted_on_this_machine(
    configured_env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
    base_url: str,
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
    """
    configure_provider(monkeypatch, base_url)

    settings = load_settings_class()()

    assert settings is not None, (
        f"`Settings` refused {base_url}, which is plain HTTP to this machine. There is no network "
        "between the process and a local model server, so there is nothing for the transport rule "
        "to protect — and refusing it makes running without a hosted provider impossible."
    )


def test_a_plain_http_provider_url_to_another_host_is_refused_when_a_key_is_set(
    configured_env: dict[str, str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A key sent in clear over a network is refused at startup rather than at the first call.

    The two things travelling over that connection are the provider key in a
    header and the student's comment in the body. SPEC §10 keeps secrets in the
    environment or the secret store, and §4 keeps a comment to the surfaces it
    names; plain HTTP to another host puts both on the wire for anything between
    here and there.

    At startup rather than on first use, because the alternative fails in the
    §3.3 fail-open direction: a call that cannot be made is an outage, an outage
    floors, and the misconfiguration is invisible while participation credit is
    handed out on a character count.

    The exception *type* is not asserted here — that is E0-01's subject and
    `tests/unit/test_create_app_startup_errors.py` owns it — and neither is the
    message, which the test below reads from the surface an operator actually
    sees. `pytest.raises` is the whole assertion, deliberately: an
    `assert refused.value is not None` after it cannot fail, and this file has
    written one before (`docs/MISTAKES.md` entry 3, its twenty-fifth instance).
    """
    configure_provider(monkeypatch, OFF_MACHINE_HTTP_URL)

    with pytest.raises(Exception):  # noqa: B017 - the type is E0-01's subject
        load_settings_class()()


def test_the_refusal_of_an_insecure_provider_url_names_the_variable_and_quotes_nothing_else(
    configured_env: dict[str, str],
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
    """
    restored = configured_env.get(REQUIRED_DEPLOYMENT_VARIABLE)
    assert restored is not None, (
        f"`.env.example` documents no {REQUIRED_DEPLOYMENT_VARIABLE}, so the control below cannot "
        "put the configuration back before the assertion that matters runs."
    )

    monkeypatch.delenv(REQUIRED_DEPLOYMENT_VARIABLE, raising=False)
    with pytest.raises(Exception) as unrelated:  # noqa: B017 - the type is E0-01's subject
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
    with pytest.raises(Exception) as refused:  # noqa: B017 - the type is E0-01's subject
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
