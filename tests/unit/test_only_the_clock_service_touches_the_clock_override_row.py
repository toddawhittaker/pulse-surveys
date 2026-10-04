"""E5.1-03 criterion 4 — one module owns the clock row.

`clock_override` is the single row that moves every survey window, term lookup
and live-enrollment check in a development stack (E2-04). Until this ticket the
row was written in a router: `backend/app/api/dev.py` deleted and inserted it
itself, beside the service that reads it. Ruling R5 of the work order moves the
three operations — the standing row, setting it, clearing it — into
`backend/app/services/clock.py`, and the criterion is that a sweep asserts the
row is read and written there and nowhere else.

**What the sweep reads.** Every `.py` file under `backend/app/`, parsed with
`ast`, for any of these currencies of the row:

  - an import of `ClockOverride`, of the module `app.models.clock`, or of
    `clock` out of the models package (`from app.models import clock`);
  - a `Name` or an `Attribute` spelled `ClockOverride` — the model reached
    through a package, `models.ClockOverride`, is the second;
  - a string constant that is not a docstring and contains `clock_override` —
    raw SQL, a `metadata.tables[...]` lookup, a `text(...)` statement;
  - a string constant equal to `ClockOverride` or containing `app.models.clock`
    — `getattr(models, "ClockOverride")` and `importlib.import_module(...)`,
    which are the same reference spelled one level out (`docs/MISTAKES.md`
    entry 53: attack the class, not today's instances).

**Where they are allowed.** `app/services/clock.py`, which owns the row;
`app/models/clock.py`, which defines it; and `app/models/__init__.py`, the model
registry's re-export that puts the table on `Base.metadata`. Tests and fixtures
that insert the row directly are outside `backend/app/` and are not this rule's
business.

**Disclosed limits, stated rather than discovered** (`docs/MISTAKES.md` entry
14). A reference assembled at runtime — `"clock_" + "override"` — is invisible.
So is a walk over every table on the metadata that happens to include this one,
such as a reset helper deleting from `Base.metadata.sorted_tables`; that reads
no name this sweep can see. And a file that is not Python — a SQL script, a
template — is outside the walk.

**The controls come first.** The sweep is required to *find* the references in
`services/clock.py`, a module that certainly holds them, before its silence
about any other module counts (`docs/MISTAKES.md` entry 35), and to name a
planted offender written in each currency while leaving the near misses alone
(entry 3). Every sample is written in this module. **A red in a control means
these tests are broken, not the code.**

**How a red reads.** The rule is red on an assertion naming the module and the
lines where it imports and uses `ClockOverride` — `app/api/dev.py`, before
E5.1-03 moved those writes into the clock service.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
APP_ROOT = REPO_ROOT / "backend" / "app"

# The row's three names: the model, the module that defines it, and the table.
MODEL_NAME = "ClockOverride"
MODEL_MODULE = "app.models.clock"
TABLE_NAME = "clock_override"

# The module the ruling makes the row's one owner, by its path under `backend/`.
OWNER = "app/services/clock.py"

# Where a reference is allowed, each with the reason. Paths are relative to
# `backend/`, which is how a failure names them.
ALLOWED = {
    OWNER: "R5 makes it the one module that reads and writes the row.",
    "app/models/clock.py": "It defines the model and the table.",
    "app/models/__init__.py": (
        "The model registry imports every model so the table is on `Base.metadata`, which is "
        "where migrations and the test fixtures find it."
    ),
}

# ---------------------------------------------------------------------------
# Planted offenders, one per currency, and the near misses. Written here, never
# copied out of the tree.
# ---------------------------------------------------------------------------

OFFENDERS = {
    "an import of the model": "from app.models.clock import ClockOverride\n",
    "an import of the model's module": "import app.models.clock\n",
    "a relative import of the model's module": "from ..models.clock import Anything\n",
    "the model's module imported out of the package": "from app.models import clock\n",
    "the model reached through its package": (
        "from app import models\n\n\ndef read(session):\n"
        "    return session.get(models.ClockOverride, 1)\n"
    ),
    "the model named directly": "def read(session, ClockOverride):\n    return ClockOverride\n",
    "the table in raw SQL": (
        "from sqlalchemy import text\n\nSTATEMENT = text('DELETE FROM clock_override')\n"
    ),
    "the table looked up on the metadata": (
        "def table(metadata):\n    return metadata.tables['clock_override']\n"
    ),
    "the model fetched by name": (
        "from app import models\n\nMODEL = getattr(models, 'ClockOverride')\n"
    ),
    "the model's module imported by name": (
        "import importlib\n\nMODULE = importlib.import_module('app.models.clock')\n"
    ),
}

# The near misses: the service imported and called, which is what every caller
# after this ticket does; a docstring that explains the row; and names that
# merely share a word with it.
NEAR_MISSES = "\n".join(
    [
        '"""Moves the clock through `clock_override`, by way of the clock service."""',
        "",
        "from app.services import clock",
        "from app.services.clock import now",
        "",
        "",
        "def pretend(session, instant):",
        '    """Set the `clock_override` row through the service that owns it."""',
        "    clock.set_override(session, pretend_now=instant)",
        "    return now(session)",
        "",
        "",
        "OVERRIDE_FIELD = 'pretend_now'",
        "CLOCK_TESTID = 'clock-override-state'",
        "",
    ]
)


# ---------------------------------------------------------------------------
# The sweep.
# ---------------------------------------------------------------------------


def docstring_constants(tree: ast.AST) -> set[int]:
    """The identity of every string node that is a docstring rather than a value."""
    found: set[int] = set()
    holders = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
    for node in ast.walk(tree):
        if not isinstance(node, holders):
            continue
        body = list(getattr(node, "body", []))
        if not body or not isinstance(body[0], ast.Expr):
            continue
        first = body[0].value
        if isinstance(first, ast.Constant) and isinstance(first.value, str):
            found.add(id(first))
    return found


def names_the_model_module(module: str) -> bool:
    """Whether a dotted module path, absolute or relative, ends at `models.clock`."""
    return module.split(".")[-2:] == ["models", "clock"]


def references_in(source: str, filename: str) -> list[str]:
    """Every reference to the clock row in `source`, each described with its line.

    See the module docstring for the currencies. Each is described in words a
    failure message can print, because "line 857" alone sends a reader to the
    file to find out which of five shapes it was.
    """
    tree = ast.parse(source, filename=filename)
    docstrings = docstring_constants(tree)
    found: list[str] = []
    for node in ast.walk(tree):
        line = getattr(node, "lineno", 0)
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if names_the_model_module(module):
                found.append(f"line {line}: imports from the model's module `{module}`")
            elif module.split(".")[-1:] == ["models"] and any(
                alias.name == "clock" for alias in node.names
            ):
                found.append(f"line {line}: imports the model's module out of `{module}`")
            if any(alias.name == MODEL_NAME for alias in node.names):
                found.append(f"line {line}: imports `{MODEL_NAME}`")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if names_the_model_module(alias.name):
                    found.append(f"line {line}: imports `{alias.name}`")
        elif isinstance(node, ast.Name) and node.id == MODEL_NAME:
            found.append(f"line {line}: names `{MODEL_NAME}`")
        elif isinstance(node, ast.Attribute) and node.attr == MODEL_NAME:
            found.append(f"line {line}: reaches `.{MODEL_NAME}`")
        elif (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in docstrings
            and (TABLE_NAME in node.value or MODEL_MODULE in node.value or node.value == MODEL_NAME)
        ):
            found.append(f"line {line}: a string naming the row, {node.value!r}")
    return found


def app_modules() -> dict[str, Path]:
    """Every `.py` file under `backend/app/`, keyed by its path relative to `backend/`."""
    if not APP_ROOT.is_dir():
        pytest.fail(
            f"{APP_ROOT.relative_to(REPO_ROOT)} is not a directory, so this sweep would read "
            "nothing and report every module clean."
        )
    backend = APP_ROOT.parent
    return {path.relative_to(backend).as_posix(): path for path in sorted(APP_ROOT.rglob("*.py"))}


def references_by_module() -> dict[str, list[str]]:
    """Every module under `backend/app/` that references the row, with what it references."""
    found: dict[str, list[str]] = {}
    for name, path in app_modules().items():
        try:
            references = references_in(path.read_text(encoding="utf-8"), str(path))
        except SyntaxError as failure:  # pragma: no cover - a broken source tree
            pytest.fail(
                f"{name} does not parse ({failure}), so this sweep cannot read it and would "
                "report success having skipped it."
            )
        if references:
            found[name] = references
    return found


# ---------------------------------------------------------------------------
# Controls. A red here means these tests are broken, not the code.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("shape", sorted(OFFENDERS))
def test_the_sweep_names_a_planted_offender_in_every_currency(shape: str) -> None:
    """Each way a module can reach the row is named on a sample that certainly does.

    **The mutation it kills:** a sweep that reads imports only, or names only,
    or strings only — each of which is green over a router that reaches the row
    by one of the other two. **Its near miss** is the next control. **A red
    here means this module is broken, not that the code is.**
    """
    found = references_in(OFFENDERS[shape], f"a sample holding {shape}")
    assert found, (
        f"The sweep found nothing in a sample holding {shape}:\n\n{OFFENDERS[shape]}\n"
        "A module reaching the row that way would be reported clean."
    )


def test_the_sweep_leaves_the_service_call_and_the_prose_alone() -> None:
    """Calling the clock service, and a docstring naming the row, are not references.

    After this ticket `api/dev.py` moves the clock by calling the service, and
    every module that explains itself may name the table in a docstring. A sweep
    that named either would be red against the correct tree and would be
    weakened rather than fixed. **The mutation it kills:** a sweep matching the
    word `clock` or the table name in prose. **A red here means this module is
    broken.**
    """
    found = references_in(NEAR_MISSES, "a sample calling the clock service")
    assert found == [], (
        f"The sweep named {found} in a module that only calls `app.services.clock` and names the "
        "row in its docstrings."
    )


def test_the_sweep_finds_the_references_in_the_clock_service_itself() -> None:
    """The positive canary: the owner certainly reads the row, so the sweep must see it.

    `app/services/clock.py` is the module that answers `now()` under an
    override (E2-04), so it reads the row on today's tree and after this ticket
    writes it too. A sweep that reports it clean has gone blind, and its silence
    about every other module means nothing (`docs/MISTAKES.md` entry 35).

    **The mutation it kills:** a walk rooted at the wrong directory, or one that
    parses nothing. **A red here means this module is broken, or the service no
    longer reads the row it is the owner of.**
    """
    modules = app_modules()
    assert OWNER in modules, (
        f"The walk of {APP_ROOT.relative_to(REPO_ROOT)} found no `{OWNER}`; it found "
        f"{len(modules)} modules. The clock service is where E2-04 put the override reader."
    )
    found = references_in(modules[OWNER].read_text(encoding="utf-8"), str(modules[OWNER]))
    assert found, (
        f"The sweep found no reference to the row in `{OWNER}`. That module reads the override to "
        "answer `now()`, so a sweep that cannot see it there cannot see it anywhere."
    )


# ---------------------------------------------------------------------------
# The rule.
# ---------------------------------------------------------------------------


def test_no_module_outside_the_clock_service_reads_or_writes_the_clock_row() -> None:
    """Criterion 4: `clock_override` is read and written only in `services/clock.py`.

    **The mutation it kills:** a router, a job or a seed helper that deletes or
    inserts the row itself — which is what `api/dev.py` does on today's tree —
    and a second reader that applies the override with its own arithmetic. Both
    put the meaning of the row in two places, and the next change to it lands
    in one. **The near misses it spares** are the allowed modules, each with its
    reason in `ALLOWED`, and every module that calls the service.

    **The allowances are required to exist.** An allowance naming a file that
    has moved is an exemption nobody can check, and it would quietly excuse
    whatever arrives at that path next.
    """
    modules = app_modules()
    assert modules, f"{APP_ROOT.relative_to(REPO_ROOT)} holds no Python module to sweep."

    stale = sorted(name for name in ALLOWED if name not in modules)
    assert not stale, (
        f"These allowances name no module under `backend/`: {stale}. An allowance is an argument "
        "about one file; when the file goes, the allowance goes with it."
    )

    outside = {
        name: references
        for name, references in references_by_module().items()
        if name not in ALLOWED
    }
    assert not outside, (
        "These modules reach the `clock_override` row outside the clock service:\n"
        + "\n".join(
            f"  {name}:\n" + "\n".join(f"    {reference}" for reference in references)
            for name, references in sorted(outside.items())
        )
        + "\n\nE5.1-03's ruling R5 gives `app/services/clock.py` three functions that own the row — "
        "the standing override, setting it and clearing it — and every other module calls them. "
        "A caller owns its transaction and commits; it does not import the model."
    )
