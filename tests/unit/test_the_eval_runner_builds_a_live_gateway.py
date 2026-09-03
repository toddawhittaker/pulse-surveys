"""The eval run always reaches the real provider, never the mock — ticket E2-12.

E2-07 put an OpenAI-compatible mock in the base Compose file, and ADR 0113 makes
it a service every deployment starts. `.env.example` points the application at it
so that `docker compose up` on a clean checkout classifies a comment without
calling a model anybody pays for. That is right for the application and fatal for
this gate: an eval run against `mock-ai` measures SPEC §3.3's character count
wearing a model's clothes, reports it as SPEC §9.3's precision and recall, and
writes a floor that a character count can clear forever.

So the configuration splits in two. `AI_PROVIDER_API_KEY`,
`AI_PROVIDER_BASE_URL` and `AI_PROVIDER_MODEL_NAME` describe the real provider;
`MOCK_AI_PROVIDER_API_KEY`, `MOCK_AI_PROVIDER_BASE_URL` and
`MOCK_AI_PROVIDER_MODEL_NAME` describe the mock. `AIGateway` takes a `live`
construction flag: `live=True` reads the real triple in every environment,
`live=False` reads the mock triple in development and test and the real one in a
deployment. The eval runner always passes `live=True`, and this module is what
says so.

**Two of these tests are red until the implementer's half lands** — the
construction flag and the documented configuration surface. The third is a
control over the runner, which ships in this change.

**The collision this created, and where it was repaired.** Renaming
`AI_MODEL_NAME` to `AI_PROVIDER_MODEL_NAME` falsified constants and prose in six
committed modules, none of which E2-12's implementer may touch —
`docs/MISTAKES.md` entry 22, a ticket's new rule making an earlier ticket's tests
unrunnable with the repair on the other side of the test wall. Those repairs were
made under a ruling and ship in their own commit, and each says in its own file
that the reason is the spelling the ruling struck rather than any new test
needing it.

The selection half was ruled with it: `live=False` reads the mock triple in
development and test, so a fixture pointing a `live=False` gateway anywhere in a
test process configures the mock side. Every such suite moved for that reason and
in the same commit.

**This module asserts the flag the runner passes, and not what the flag then
does.** A constructed gateway carries no evidence of how it was built, so the
construction call is the only place that property exists — and what the flag
*selects* is a different question, asked from the endpoints' side in
`tests/unit/test_the_gateway_reads_the_provider_triple_the_flag_selects.py`.
Neither covers the other: a runner passing `live=True` into a gateway that
ignores it reaches the mock, and a gateway that selects perfectly reaches the
mock anyway if the runner never passes the flag.
"""

from __future__ import annotations

import importlib
import inspect
import sys
from pathlib import Path
from types import ModuleType
from typing import Any, ClassVar
from urllib.parse import urlsplit

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

GATEWAY_MODULE = "app.ai.gateway"
GATEWAY_CLASS = "AIGateway"
LIVE_FLAG = "live"

# The six variables the configuration split settles. Three describing the
# provider a deployment and every eval run reach, three describing the mock a
# development stack reaches.
REAL_TRIPLE = (
    "AI_PROVIDER_API_KEY",
    "AI_PROVIDER_BASE_URL",
    "AI_PROVIDER_MODEL_NAME",
)
MOCK_TRIPLE = (
    "MOCK_AI_PROVIDER_API_KEY",
    "MOCK_AI_PROVIDER_BASE_URL",
    "MOCK_AI_PROVIDER_MODEL_NAME",
)

# The name the model identifier is documented under today, and which the split
# renames. It is unqualified — it says which model without saying whose — and
# once two providers are configured at once there is no honest answer to which of
# them it means.
UNQUALIFIED_MODEL_VARIABLE = "AI_MODEL_NAME"

# ADR 0113's host: the Compose service name the mock answers on. Compared as a
# host rather than as a substring, exactly as that record requires — an
# institution's own `https://mock-ai.example.edu/v1` is an ordinary address and
# is not this service.
MOCK_HOST = "mock-ai"


def eval_module(name: str) -> ModuleType:
    """Import one of `tests/evals/`'s modules, or fail naming the deliverable."""
    root = str(REPO_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)
    try:
        return importlib.import_module(name)
    except ModuleNotFoundError as failure:
        if failure.name is not None and (
            name == failure.name or name.startswith(f"{failure.name}.")
        ):
            pytest.fail(f"There is no `{name}` module. E2-12 puts the eval runner there.")
        raise


class RecordingGateway:
    """Stands in for `AIGateway` and remembers how it was constructed.

    It is what makes "the runner builds its gateway live" observable at all. The
    flag decides which of two configured endpoints the gateway will talk to, and
    nothing about the object afterwards says which flag produced it — so the
    construction call is the only place the property exists.
    """

    calls: ClassVar[list[dict[str, Any]]] = []

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        RecordingGateway.calls.append({"args": args, "kwargs": kwargs})


def host_of(url: str) -> str | None:
    """The host component of a URL, normalised — ADR 0113's comparison, not a substring one."""
    host = urlsplit(url).hostname
    return None if host is None else host.rstrip(".").lower()


def test_the_gateway_takes_a_live_construction_flag_that_defaults_to_false(
    configured_env: dict[str, str],
) -> None:
    """The flag that decides which of the two configured providers a gateway reaches.

    `live=False` is the default because every caller except this one wants it: the
    submit path in development talks to `mock-ai`, and a default of `True` would
    point a clean `docker compose up` at a paid endpoint the checkout has no
    credential for. SPEC §14.3 requires that checkout to come up.

    `live=True` is the eval runner's, and it has to mean the real triple *in every
    environment* — a run on a developer's machine and a run in CI measure the same
    thing or they measure nothing comparable.

    **The default is asserted as well as the parameter**, and it is the half that
    is easy to get wrong in the expensive direction. A flag that exists and
    defaults to `True` turns every development classification into a paid call and
    every test that forgets to pass it into a network round trip, and nothing about
    that fails loudly — it just costs money and leaves the machine.

    **The mutation this kills:** add the parameter and default it to `True`, or
    read the environment inside the gateway instead of taking a flag — which puts
    the decision back where the eval runner cannot make it.
    """
    module = eval_module(GATEWAY_MODULE)
    gateway_class = getattr(module, GATEWAY_CLASS, None)
    assert gateway_class is not None, (
        f"`{GATEWAY_MODULE}` exposes no `{GATEWAY_CLASS}`. SPEC §7.4: 'All model calls go "
        f"through one internal `{GATEWAY_CLASS}`'."
    )

    parameters = inspect.signature(gateway_class.__init__).parameters
    assert LIVE_FLAG in parameters, (
        f"`{GATEWAY_CLASS}` takes {sorted(name for name in parameters if name != 'self')} "
        f"and no `{LIVE_FLAG}` flag. Without it the eval runner cannot say which of the two "
        "configured providers it is measuring, and in development it would measure "
        "`mock-ai` — a character count reported as SPEC §9.3's precision and recall."
    )

    default = parameters[LIVE_FLAG].default
    assert default is False, (
        f"`{GATEWAY_CLASS}`'s `{LIVE_FLAG}` flag defaults to {default!r} rather than False. "
        "Every caller except the eval runner wants the mock in development, and a default "
        "of True sends a clean `docker compose up` — and every test that does not pass the "
        "flag — to a paid endpoint. That failure is silent: it costs money and puts comment "
        "text on the wire, and nothing goes red."
    )


def test_the_eval_runner_builds_its_gateway_live(
    monkeypatch: pytest.MonkeyPatch, configured_env: dict[str, str]
) -> None:
    """The runner passes `live=True`, and that is the only place the property is visible.

    A gateway object carries no evidence of which flag built it, so this asserts
    the construction call: `AIGateway` on `app.ai.gateway` is replaced with a
    recorder, the runner's own factory is called, and what it passed is read off
    the recording.

    Substituted on the module rather than injected, because the runner reaches the
    class through the module object at call time — which is what lets a
    substitution here work at all, and is the reason it is written that way.

    **No provider is reached.** The recorder replaces the gateway entirely and the
    returned classifier is never called, so nothing in this test opens a socket.

    **The mutation this kills:** `AIGateway()` in the runner, taking the default —
    which on a developer's machine or in the test environment reads the mock
    triple, measures E2-07's character rule, and reports the number as a model's.
    A run like that passes every other test in this repository.
    """
    RecordingGateway.calls = []
    gateway_module = eval_module(GATEWAY_MODULE)
    monkeypatch.setattr(gateway_module, GATEWAY_CLASS, RecordingGateway, raising=False)

    live = eval_module("tests.evals.live")
    live.build_validity_classifier()

    assert RecordingGateway.calls, (
        "the runner's classifier factory built no gateway at all, so nothing it measures "
        "goes through the one internal gateway SPEC §7.4 requires every model call to use."
    )
    passed = RecordingGateway.calls[-1]["kwargs"]
    assert passed.get(LIVE_FLAG) is True, (
        f"the eval runner constructed its gateway with {passed!r}. It must pass "
        f"`{LIVE_FLAG}=True` explicitly: with the default, a run in development or in the "
        "test environment reads the `MOCK_AI_PROVIDER_*` triple and measures E2-07's "
        "character rule, then writes that score down as SPEC §9.3's floor."
    )


def test_the_documented_configuration_names_both_provider_triples(
    documented_env: dict[str, str], env_example_path: Path
) -> None:
    """`.env.example` is the configuration documentation (SPEC §6.3), and it has to say six things.

    Three variables cannot describe two providers. Today one base URL, one model
    name and one key point at whichever endpoint the file happens to name, and the
    file names the mock — so the only way to reach a real provider is to overwrite
    the values the development stack needs, and the only way to keep the
    development stack working is to have no real provider configured at all. The
    eval runner needs both at once.

    **The mutation this kills:** add the `live` flag to the gateway and leave the
    configuration as one triple, so `live=True` and `live=False` read the same
    three variables and the flag decides nothing.
    """
    assert documented_env, (
        f"{env_example_path} parsed to no variables at all, so every assertion below would "
        "pass over an empty file."
    )

    missing = [name for name in (*REAL_TRIPLE, *MOCK_TRIPLE) if name not in documented_env]
    assert not missing, (
        f"{env_example_path.name} documents neither of these: {missing}.\n"
        f"  the real provider's triple: {list(REAL_TRIPLE)}\n"
        f"  the mock's triple:          {list(MOCK_TRIPLE)}\n"
        "\n"
        "SPEC §6.3 makes this file the configuration surface, and `CLAUDE.md` requires a "
        "ticket that adds a variable to add its name here in the same pull request."
    )


def test_the_documented_configuration_no_longer_names_the_unqualified_model_variable(
    documented_env: dict[str, str], env_example_path: Path
) -> None:
    """`AI_MODEL_NAME` says which model without saying whose, and now there are two.

    It was an honest name while one endpoint was configured. With a real provider
    and a mock described side by side it is ambiguous, and an ambiguous
    configuration name is one that gets read by whichever of the two readers looks
    first — a gateway built `live=True` picking up the mock's model identifier, and
    then storing it in a `classification` row as the model that produced a verdict
    (ADR 0031). That is an audit record that is wrong and looks right.

    **This test cannot be green while five committed modules and one fixture still
    name the old variable**, and repairing those is on the test author's side of
    the heavy-lane wall rather than the implementer's. It is `docs/MISTAKES.md`
    entry 22, it is named in this ticket's report, and it is a ruling rather than
    something to work around by softening this assertion.

    **The mutation this kills:** add `AI_PROVIDER_MODEL_NAME` beside
    `AI_MODEL_NAME` and leave both, which satisfies the test above and leaves two
    names for one value — the state where a reader picks one and a writer sets the
    other.
    """
    assert documented_env, f"{env_example_path} parsed to no variables at all."
    assert UNQUALIFIED_MODEL_VARIABLE not in documented_env, (
        f"{env_example_path.name} still documents `{UNQUALIFIED_MODEL_VARIABLE}`, alongside "
        f"`{REAL_TRIPLE[2]}` and `{MOCK_TRIPLE[2]}`. Three names for two values leaves one "
        "of them read by nothing and set by somebody, which surfaces as a gateway using a "
        "model identifier nobody configured."
    )


def test_the_real_providers_base_url_is_documented_blank_and_the_mocks_is_the_mock(
    documented_env: dict[str, str], env_example_path: Path
) -> None:
    """The real endpoint is not shipped, the mock's is, and neither is the other.

    ADR 0113 refuses a provider base URL whose host is `mock-ai` outside
    development, because "the mock runs in every deployment that runs the base
    Compose file, and a deployment pointed at it would store a character count as
    a classification under a real prompt version and a real model id". The
    configuration split extended that: the *real* triple may never name the mock
    in any environment, because the eval runner reads it in development too.

    **E2-12's security review found the same hazard with the polarity reversed,
    and it is why `AI_PROVIDER_BASE_URL` is now documented blank.** The entry
    shipped carrying a working public endpoint, and beside a blank
    `AI_PROVIDER_API_KEY` that let a deployment which configured everything else
    and left the AI block alone — because it looked configured already — start
    cleanly and post §3.3's prompts, student comment text and all, to a third
    party under a placeholder bearer. The field is required with no default, so a
    blank refuses at startup and names itself; the endpoint belongs in the comment
    beside the entry, where an operator copies it on purpose.

    **The two properties are asserted separately, because they fail separately.**
    That the real entry carries nothing is the new one. That the real entry, if it
    ever carries anything, does not name the mock is the old one, and it is kept
    rather than folded away: a blank passes it trivially today, and it is what
    catches the next edit that fills the line in with the wrong address.
    `test_the_documented_configuration_names_both_provider_triples` above holds
    the entry present, so "blank" here cannot become "deleted".

    **The host is compared as a host** (ADR 0113, ADR 0077): a substring search
    would refuse `https://mock-ai.example.edu/v1`, an address a real institution
    could hold, and the four spellings in
    `tests/unit/test_ai_provider_configuration.py` are what a host comparison
    survives.

    **The mutation this kills:** put an endpoint back on the real line — any
    endpoint, including a correct one, because the defect was that it started
    rather than that it was wrong; and rename the variables while leaving both
    pointing at one value, which is what a search-and-replace produces. **The near
    miss that must stay green:** the endpoint written in the *comment* beside the
    entry, which is where it now belongs and which `documented_env` does not read.
    """
    assert documented_env, f"{env_example_path} parsed to no variables at all."

    real = documented_env.get(REAL_TRIPLE[1], "")
    mock = documented_env.get(MOCK_TRIPLE[1], "")

    assert not real.strip(), (
        f"{env_example_path.name} documents `{REAL_TRIPLE[1]}` as {real!r}, and it must be "
        "blank.\n"
        "\n"
        "A working endpoint on that line, beside a blank key, is a deployment that "
        "configured everything else and left the AI block alone starting cleanly and "
        "sending §3.3's prompts — student comment text included — to a third party under a "
        "placeholder bearer token. Nothing fails and nothing warns. The field is required "
        "with no default, so blank refuses at startup and names itself, which is the "
        "behaviour a forgotten setting should have.\n"
        "\n"
        "The endpoint belongs in the comment above the entry, where an operator copies it "
        "deliberately."
    )

    assert host_of(real) != MOCK_HOST, (
        f"`{REAL_TRIPLE[1]}` is documented as {real!r}, whose host is the in-repo mock. "
        "That is the triple a gateway built `live=True` reads in every environment, so a "
        "local `make evals` would measure E2-07's character rule and record the score as "
        "SPEC §9.3's precision and recall."
    )
    assert host_of(mock) == MOCK_HOST, (
        f"`{MOCK_TRIPLE[1]}` is documented as {mock!r}, whose host is not `{MOCK_HOST}`. "
        "That triple is what `docker compose up` on a clean checkout classifies through "
        "(SPEC §14.3), and pointing it anywhere else either breaks the clean checkout or "
        "sends a development stack's comments to a paid endpoint."
    )
