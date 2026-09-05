"""FIX-03 — every test starts from the documented environment, and can opt out of it.

`docs/MISTAKES.md` entry 40 records a failure class this repository has now hit
three times: the suite runs under an environment nobody chose, and it is a
different one in CI. Application modules build `Settings()` at import time
(`backend/app/db.py`, and the Celery application per ADR 0010), so a test that
reaches one through a transitive import needs the environment laid down before it
runs. On a developer's machine the shell and `.env` supply it and the gap is
invisible; CI has no `.env`, and under `pytest-xdist` the failure appears only on
a worker where no earlier test happened to run `configured_env` first — which is
why it survives repeated green local runs and three verified build rounds.

FIX-03 removes the class rather than the instance. `documented_environment_baseline`
in `tests/conftest.py` is session-scoped and autouse, so `.env.example`'s documented
values are in `os.environ` on every worker before any test runs; `unconfigured_env`
in `tests/fixtures/repo.py` is the opt-out for a test whose subject is what an
unconfigured application does.

**This module is the machinery's own proof, and it is written in two halves.**

The *controls* must be green: they say the baseline ran and the opt-out really
cleared. A red control means the machinery here is broken, not that the code under
it is wrong — that is the rule new machinery ships under, and it matters more than
usual here because everything else in the suite now rests on a fixture nobody
declares. A control that has quietly stopped measuring anything reports exactly
what a working one reports.

The *canary pair* is criterion 1 in both directions, on the module the ticket names:
`app.db` imports cleanly with no environment fixture declared at all, and the same
import is refused when the opt-out clears the environment. One direction on its own
proves nothing. A baseline that laid nothing down passes the refusal and fails the
import; an opt-out that cleared nothing passes the import and fails the refusal.

Every import here goes through `import_app_module`, which drops every `app.*` module
from `sys.modules` first. Without it a module cached by an earlier test answers with
whatever environment *that* test set, and this module would be measuring test order
(`docs/MISTAKES.md` entry 3).

**What this module cannot assert.** Criterion 1 says the proof is "running the suite
with the ambient application variables unset, not by argument", and criterion 3 is
about a whole suite run; neither is a property a test can hold. Both are run-level,
and the target asserted at the foot of this module is what makes that run one
command rather than a dance with `.env` moved aside by hand.
"""

import os
import re
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
MAKEFILE_PATH = REPO_ROOT / "Makefile"

# The module the ticket names as the one that builds `Settings()` at import time.
# Named rather than discovered, because the ticket names it: "application modules
# build `Settings()` at import time (`backend/app/db.py`; the Celery application,
# per ADR 0010)". If it moves, this constant moves with it.
DB_MODULE = "app.db"

# The documented variable the controls below read, and the one `app.db` needs. It is
# this suite's choice of witness rather than the ticket's, so it is written once:
# `DATABASE_URL` is required, has no default, and is the variable E1-11's sixteen CI
# reds named. Its documented value is `.env.example`'s uninterpolated template —
# `parse_dotenv` does not expand `${...}` — which is why an equality assertion
# against it cannot be satisfied by a developer's shell or by a `.env` that some
# loader interpolated on the way in.
SENTINEL_VARIABLE = "DATABASE_URL"

# FIX-03 scope item 3. The name is settled by the ticket's work order; what the
# recipe does is the implementer's, and nothing here reads it.
SCRUBBED_GATE_TARGET = "test-as-ci"

# A target this repository already declares, for the control that the reader below
# can find one at all, and a name nothing declares, for its pair. `docker-build` is
# read by `tests/unit/test_the_docker_gate_and_the_makefile_run_the_same_checks.py`,
# which asserts it has a recipe — so a red on the control here is this module's
# reader, not a missing target.
DECLARED_TARGET = "docker-build"
UNDECLARED_TARGET = "no-target-is-spelled-this-way-fix-03"


def configuration_error() -> type[BaseException]:
    """The error type the application promises its callers, imported inside the test.

    Named rather than caught as `Exception`, for the reason
    `tests/unit/test_oidc_provider_configuration.py` gives on the same import: a bare
    `Exception` is satisfied by an `AttributeError` out of a renamed symbol, which is
    a broken test reading as a refused configuration — the exact inversion this
    module exists to prevent.

    Importing `app.config` builds nothing; it is `app.db` that constructs `Settings`
    at import, which is what the pair below is about.
    """
    from app.config import ConfigurationError

    return ConfigurationError


def declares_target(makefile: str, target: str) -> bool:
    """Whether the Makefile declares `target` — a name at column zero, then a colon.

    Deliberately says nothing about the recipe. FIX-03's work order settles the
    target's *name*; what it runs is the implementer's to write, and a test that read
    the recipe would be this suite choosing it.

    Anchored at the start of a line, so a `.PHONY:` listing that mentions the name is
    not counted as declaring it: a phony declaration without a rule is a target make
    has nothing to run for.
    """
    return re.search(rf"(?m)^{re.escape(target)}\s*:", makefile) is not None


# ---------------------------------------------------------------------------
# Controls. These must be green: a red one means the machinery in this module is
# broken rather than that the fixtures under it are wrong.
# ---------------------------------------------------------------------------


def test_the_sentinel_variable_is_one_env_example_actually_documents(
    documented_env: dict[str, str],
) -> None:
    """A control on the witness the two baseline assertions below are made through.

    **A red here means these tests are broken, or `.env.example` has been renamed
    around this variable.** `SENTINEL_VARIABLE` is written out rather than derived,
    which is right for a one-value witness a reviewed diff should have to change —
    but a written-out name can go stale without anything failing, and a control read
    through a name the file does not document would report the baseline absent
    whatever the baseline did.

    **The mutation this kills:** `SENTINEL_VARIABLE` set to a name `.env.example`
    does not carry. **Its pair on the other side:** the empty-mapping guard, since an
    `.env.example` that failed to parse documents nothing and would make every
    assertion in this module vacuous rather than false.
    """
    assert documented_env, (
        "`.env.example` documented no variables, so the baseline lays nothing down and every "
        "assertion in this module is about an empty mapping. `tests/unit/test_env_example_sync.py` "
        "says what that file is supposed to hold."
    )
    assert SENTINEL_VARIABLE in documented_env, (
        f"`.env.example` does not document {SENTINEL_VARIABLE!r}, which is the variable this "
        f"module reads the baseline through. It documents {sorted(documented_env)}. Either that "
        "file has moved on or this constant has gone stale; the constant is the one line that "
        "changes."
    )


def test_the_documented_environment_is_in_place_with_no_fixture_laying_it_down(
    documented_env: dict[str, str],
) -> None:
    """A control: the baseline ran, in this process, for a test that declared nothing.

    **A red here means the session baseline did not run** — and everything else FIX-03
    claims rests on it. `documented_env` is asked for because it reads `.env.example`
    and touches `os.environ` not at all, so it cannot be what put the value there;
    no fixture in this test's chain sets an environment variable.

    Asserted as **equality with the documented value**, not as presence. Presence is
    satisfied by a developer's own shell, by a `.env` some loader leaked, and by a
    baseline written as `setdefault` — three ways for CI and a laptop to keep
    disagreeing while this test stays green. The documented value is the
    uninterpolated `${...}` template, which no shell and no interpolating loader ever
    produces, so equality is a claim about this fixture and nothing else.

    **The mutations this kill:** the baseline dropped, made non-autouse, given a
    narrower scope than the session, or written to fill gaps rather than to override.
    """
    documented = documented_env.get(SENTINEL_VARIABLE)
    assert documented is not None, (
        f"`.env.example` documents no {SENTINEL_VARIABLE}, so this control has nothing to compare "
        "against. `test_the_sentinel_variable_is_one_env_example_actually_documents` owns that "
        "failure and says what to change."
    )

    assert os.environ.get(SENTINEL_VARIABLE) == documented, (
        f"`os.environ[{SENTINEL_VARIABLE!r}]` is {os.environ.get(SENTINEL_VARIABLE)!r} and "
        f"`.env.example` documents {documented!r}. `documented_environment_baseline` in "
        "tests/conftest.py is session-scoped and autouse so that every test on every xdist worker "
        "starts from the documented values whether it asks for them or not, and it sets them "
        "unconditionally rather than filling gaps — parity with CI means the documented value "
        "wins. Without it this suite is back to being green on whatever the machine exported "
        "(`docs/MISTAKES.md` entry 40)."
    )


def test_the_opt_out_clears_every_variable_env_example_documents(
    unconfigured_env: dict[str, str],
) -> None:
    """A control: the opt-out really emptied the environment the baseline filled.

    **A red here means the opt-out is broken**, and every refusal asserted under it —
    starting with the canary's second half below — is passing or failing for a reason
    it did not choose. This is the exact direction `docs/MISTAKES.md` entry 3 warns
    about: an opt-out that cleared nothing leaves a refusal test asserting that a
    fully configured application refuses, which is either a false red or, worse,
    a green produced by some other rule.

    Every documented name is checked rather than the witness alone, because the
    fixture's claim is about the whole documented set: a partial clear leaves the
    refusal below naming whichever variable happened to survive.

    **The mutation this kills:** `unconfigured_env` reduced to the one or two names a
    caller happens to care about, or its loop dropped altogether.
    """
    assert unconfigured_env, (
        "`unconfigured_env` cleared no names, so this test — and every refusal asserted under "
        "that fixture — runs in a fully configured process while reporting a bare one. An "
        "`.env.example` that failed to parse is the way that happens."
    )

    still_set = {name: os.environ[name] for name in unconfigured_env if name in os.environ}
    assert not still_set, (
        f"After `unconfigured_env`, `os.environ` still carries {sorted(still_set)}. The fixture "
        "removes every name `.env.example` documents so that a test about an unconfigured "
        "application is about one; a name that survives is a value the session baseline laid down "
        "and the opt-out did not take back."
    )


# ---------------------------------------------------------------------------
# The canary pair — criterion 1, in both directions.
# ---------------------------------------------------------------------------


def test_the_module_that_builds_settings_at_import_imports_with_no_environment_fixture(
    import_app_module: Callable[[str], ModuleType | None],
) -> None:
    """Criterion 1: `app.db` imports on a bare worker, with nothing declared for it.

    **This test declares no environment fixture on purpose, and that is its whole
    subject.** It is written the way the tests that keep breaking are written — an
    author who did not notice that the module reaches `Settings()` at import — and it
    has to pass anyway. Today it would pass on a developer's machine off `.env` and
    fail in CI, on whichever xdist worker ran it before anything called
    `configured_env`; after FIX-03 it passes in both, because the documented values
    are already in the process.

    Through `import_app_module` rather than a plain `import`, so a module some earlier
    test already imported cannot answer for this one. With a cached `app.db` in
    `sys.modules` the import here is a dictionary lookup and would succeed against a
    baseline that never ran.

    **The mutations this kills:** `documented_environment_baseline` dropped, made
    non-autouse, or scoped narrower than the session — each of which leaves a worker
    that runs this test first with nothing laid down. **The near miss that must stay
    green:** the refusal below, which is the same import with the environment
    deliberately taken away; a baseline that also disabled the opt-out would pass this
    and fail that.

    Criterion 1 asks for the proof to be a run rather than an argument, and this test
    cannot make it: it says the import succeeds in *this* process. The run under
    `make test-as-ci`, with the ambient variables scrubbed, is what makes it a claim
    about a bare worker.
    """
    try:
        module = import_app_module(DB_MODULE)
    except Exception as failure:
        pytest.fail(
            f"Importing `{DB_MODULE}` with no environment fixture declared raised {failure!r}. "
            "That module builds `Settings()` at import time, so it needs the documented "
            "environment in place before any test body runs — which is what "
            "`documented_environment_baseline` in tests/conftest.py is for. Every recurrence in "
            "`docs/MISTAKES.md` entry 40 is this failure reached through one import chain or "
            "another, and it is invisible on a machine that has a `.env`."
        )

    assert module is not None, (
        f"There is no `{DB_MODULE}` module. FIX-03 names it as the module that builds `Settings()` "
        "at import time; if the engine has moved, this module's `DB_MODULE` constant is the one "
        "line that changes."
    )


def test_the_same_import_is_refused_when_the_opt_out_clears_the_environment(
    unconfigured_env: dict[str, str],
    import_app_module: Callable[[str], ModuleType | None],
) -> None:
    """The pair: with the documented values taken away, that import refuses, naming the field.

    Same module, same import machinery, one fixture different. Without this direction
    the test above is satisfied by an `app.db` that needs no configuration at all,
    and the baseline would be vouched for by an import that never read it.

    **Which layer refused is pinned, not just that something raised.** The type is
    `app.config.ConfigurationError` — the project's own error, which E0-02's startup
    handler catches and which does not carry the input mapping the way pydantic's
    does — and the message has to name the variable, because a refusal an operator
    cannot act on is a different behaviour from a refusal. A bare `pytest.raises` here
    would be green for an `ImportError`, for an `AttributeError` out of a renamed
    symbol, and for a socket error from an engine that connected eagerly.

    **The mutations this kills:** `unconfigured_env`'s `delenv` loop dropped, which
    leaves the baseline's values in place and this import succeeding; and the
    fixture's `monkeypatch.chdir` dropped, which leaves `Settings` reading the
    repository root's own `.env` through `env_file` and the import succeeding again.
    That second one only bites where a `.env` exists — a developer's machine, not CI —
    which is the asymmetry entry 40 is made of, and it is why the fixture does the
    chdir first.

    **The near miss that must stay green:** the test above, the same import with the
    baseline left in place.
    """
    assert unconfigured_env, (
        "`unconfigured_env` cleared no names, so this refusal would be asserted against a fully "
        "configured process. `test_the_opt_out_clears_every_variable_env_example_documents` owns "
        "that failure."
    )
    assert SENTINEL_VARIABLE in unconfigured_env, (
        f"{SENTINEL_VARIABLE} is not among the names the opt-out clears, so the message assertion "
        "below is about a variable this test did not remove."
    )

    with pytest.raises(configuration_error(), match=f"(?i){SENTINEL_VARIABLE}"):
        import_app_module(DB_MODULE)


# ---------------------------------------------------------------------------
# Scope item 3 — CI's configuration, reproducible locally in one command.
# ---------------------------------------------------------------------------


def test_the_makefile_declares_a_target_that_runs_the_gate_scrubbed() -> None:
    """FIX-03 scope item 3: one command runs the pytest gate the way CI runs it.

    `make ci` sources `.env`, and CI's pytest gate has none, so a green `make ci` does
    not prove the pytest gate green — that sentence is entry 40's own, written after
    E1-11's sixteen reds. `CONTRIBUTING.md` leaves moving `.env` aside to hand, and a
    dance nobody runs is a gate nobody has. This asserts the target exists so the
    dance is one command.

    **Only the name is asserted, deliberately.** What the recipe does is the
    implementer's to write; a test that read it would make this suite the author of a
    decision the ticket left to the diff. What the target is *for* is not assertable
    at all — "the full suite is green under it" is a run, and the run is the proof
    criteria 1 and 3 both ask for.

    **The mutation this kills:** the target absent, which is HEAD, or renamed so that
    the command CONTRIBUTING and entry 40 will point at does not exist. **The controls
    that say this reader works:** the two tests below, one in each direction.
    """
    assert MAKEFILE_PATH.is_file(), (
        f"{MAKEFILE_PATH} does not exist. It is the local half of every CI gate, and without it "
        "this test would be reporting a missing target when what is missing is the file."
    )

    assert declares_target(MAKEFILE_PATH.read_text(encoding="utf-8"), SCRUBBED_GATE_TARGET), (
        f"The Makefile declares no `{SCRUBBED_GATE_TARGET}` target. FIX-03 scope item 3 asks for "
        "one command that runs the pytest gate with the ambient application variables scrubbed to "
        "the documented values, so this failure class fails on the author's machine rather than an "
        "hour later in CI."
    )


def test_the_target_reader_finds_a_target_the_makefile_already_declares() -> None:
    """A control: the reader above can find a target that is really there.

    **A red here means this module's reader is broken, not that a target is missing.**
    A reader that matched nothing would report every target absent, including the one
    the test above is about — a red that reads as a missing deliverable and sends the
    implementer to write something that is already written.

    `docker-build` is the witness because another module already asserts it has a
    recipe, so its presence is not this module's assumption.
    """
    assert MAKEFILE_PATH.is_file(), (
        f"{MAKEFILE_PATH} does not exist, so this control read nothing and would report the reader "
        "broken when what is missing is the file."
    )

    assert declares_target(MAKEFILE_PATH.read_text(encoding="utf-8"), DECLARED_TARGET), (
        f"`declares_target` cannot find the `{DECLARED_TARGET}` target, which this repository does "
        "declare — `tests/unit/test_the_docker_gate_and_the_makefile_run_the_same_checks.py` reads "
        "its recipe. The reader in this module is what is wrong."
    )


def test_the_target_reader_does_not_find_a_target_the_makefile_does_not_declare() -> None:
    """The pair: a reader that answers yes to everything proves nothing.

    Without this, `declares_target` could be `return True` and the target test above
    would pass against a Makefile that never gained the target — green for a reason
    unrelated to what it asserts (`docs/MISTAKES.md` entry 3).

    **The mutation this kills:** a reader loosened to search the whole file text
    rather than to match a declaration at the start of a line, which would count a
    mention in a comment or in a `.PHONY:` list as a target with a recipe.
    """
    assert MAKEFILE_PATH.is_file(), (
        f"{MAKEFILE_PATH} does not exist, so this control read nothing and would pass against any "
        "reader at all."
    )

    assert not declares_target(MAKEFILE_PATH.read_text(encoding="utf-8"), UNDECLARED_TARGET), (
        f"`declares_target` found a `{UNDECLARED_TARGET}` target, which nothing declares. The "
        "reader answers for names that are not there, so the target assertion above says nothing."
    )
