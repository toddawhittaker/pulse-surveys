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

**The key's variable is not named here.** E0-13 spells no variable and no field,
so both are found — the `.env.example` entry by the words in its name, and the
`Settings` field by the words in *its* name — and one test requires the two to be
the same thing. That interlock is the point: a field that resolves some other
variable, or an entry no field reads, is the shape
`tests/unit/test_env_example_sync.py` exists for, and this file would otherwise
be asserting masking on a value nothing configures.

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

# An obvious fake: nothing here resembles a real credential and nothing was copied
# from a working `.env` (CLAUDE.md, secrets). Long and unlikely-looking so a
# fragment appearing in a rendering is unambiguously a leak rather than a
# coincidence. Named `...CREDENTIAL` rather than `...KEY` so ruff's S105 keeps
# flagging the real thing; `tests/conftest.py` made the same choice.
FAKE_PROVIDER_CREDENTIAL = "fake-ai-provider-Qv7ZmXt4Ld9RbNsW"

# Length of the contiguous run of a secret that counts as leaked. Checking for the
# whole value is not enough: pydantic elides the middle of a long repr, so a leak
# can print all but one character and still not contain the exact string.
# Truncation is not redaction. Same length and same reason as
# `tests/unit/test_config_settings.py`.
LEAK_FRAGMENT_LENGTH = 8

# A required deployment variable, removed to force a configuration failure so the
# error it raises can be searched. Its own absence is E0-01's subject; here it is
# only the cause of an exception that has the provider key in scope.
REQUIRED_DEPLOYMENT_VARIABLE = "DATABASE_URL"

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
        f"The AI provider key leaked into {surface}: {fragments}. E0-13's scope calls it a masked "
        "key and its definition of done sends the security review after 'the provider key "
        f"reaching a log or an error message'. The full text was:\n{rendered}"
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
                f"The AI provider key leaked into {where}() of the raised "
                f"{type(link).__name__}: {fragments}. The full text was:\n{rendering}"
            )
        errors = getattr(link, "errors", None)
        if callable(errors):
            payload = json.dumps(errors(), default=str)
            fragments = leaked_fragments(payload, FAKE_PROVIDER_CREDENTIAL)
            assert not fragments, (
                f"The AI provider key leaked into the structured payload of "
                f"{type(link).__name__}.errors(): {fragments}."
            )


# ---------------------------------------------------------------------------
# The other secret, in the other place
# ---------------------------------------------------------------------------


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
