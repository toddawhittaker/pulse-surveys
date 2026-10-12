"""Every caller of `section_benchmarks` names the reader — E9-05's fix round, P2.

**Why.** `section_benchmarks(…, scope)` takes the leadership reader into the seal
(SPEC §5.1: "A leadership reader is sealed against too"). With `scope=None` as a
default, a later leadership caller that forgot the argument would be sealed
against the instructors of the reported section only, and serve a leader a
figure thin enough to subtract with her purview — silently, because the call
still works. So the parameter has no default: it is keyword-only and required,
and every instructor caller writes `scope=None` where it means "no reader".

**Two checks.** The signature has no default for `scope`; and every call under
`backend/app/` passes `scope=` as a keyword, read off the syntax tree. A call
that hands its arguments through `**` is an offender, because the sweep cannot
see whether `scope` is among them; so is a reference to the function that is not
a call (stored, passed or aliased), because what calls it later is out of sight.

**Controlled in both directions** (`docs/MISTAKES.md` entries 3, 35 and 53): a
planted tree holding a forgetful call by name, through an import alias, through
an aliased module, a `**` call and a stored reference, beside the allowed shapes
and a longer name; and the real tree required to be *found* holding at least one
call, so a misspelt name cannot make the sweep vacuous. **Disclosed limit**
(entry 14): a name assembled at run time is not matched; nothing outside
`backend/app/` is read.

**Which failure a red is on the tree before the fix:** the signature test FAILS
on the `None` default, and the real-tree sweep FAILS listing the callers that
rely on it. The controls pass.
"""

import ast
import importlib
import inspect
from pathlib import Path

import pytest

pytestmark = pytest.mark.invariant

REPO_ROOT = Path(__file__).resolve().parents[2]
APP_ROOT = REPO_ROOT / "backend" / "app"
THE_MODULE = "app.services.benchmarks"
THE_FUNCTION = "section_benchmarks"
THE_READER = "scope"

PASSES_THE_READER = "passes scope="
FORGETS_THE_READER = "a call without scope="
HIDES_THE_READER = "a call through ** the sweep cannot read"
NOT_A_CALL = "a reference that is not a call"


def call_sites(source: str, where: str) -> list[tuple[int, str]]:
    """Every reference to `section_benchmarks` in one module, as (line, verdict).

    A reference is the name (or an import alias bound to it) or an attribute of
    that name; strings and docstrings are not references here, because a string
    cannot be called without a `getattr`, which is itself a non-call reference
    to the module only — the disclosed limit.
    """
    try:
        tree = ast.parse(source, filename=where)
    except SyntaxError as failure:  # pragma: no cover - a broken source tree
        pytest.fail(f"{where} does not parse ({failure}); this sweep would report it clean.")
    aliases = {THE_FUNCTION}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == THE_FUNCTION and alias.asname:
                    aliases.add(alias.asname)

    def names_it(node: ast.AST) -> bool:
        return (isinstance(node, ast.Name) and node.id in aliases) or (
            isinstance(node, ast.Attribute) and node.attr == THE_FUNCTION
        )

    called: set[int] = set()
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and names_it(node.func):
            called.add(id(node.func))
            keywords = [keyword.arg for keyword in node.keywords]
            if THE_READER in keywords:
                verdict = PASSES_THE_READER
            elif None in keywords:
                verdict = HIDES_THE_READER
            else:
                verdict = FORGETS_THE_READER
            found.append((node.lineno, verdict))
    for node in ast.walk(tree):
        if names_it(node) and id(node) not in called:
            found.append((node.lineno, NOT_A_CALL))
    return sorted(found)


def sites_under(root: Path) -> list[tuple[str, str]]:
    """Every reference under `root`, as ("path:line", verdict), in path then line order."""
    out: list[tuple[str, str]] = []
    for path in sorted(root.rglob("*.py")):
        relative = path.relative_to(root)
        for line, verdict in call_sites(path.read_text(encoding="utf-8"), str(relative)):
            out.append((f"{relative}:{line}", verdict))
    return out


def offenders_under(root: Path) -> list[tuple[str, str]]:
    return [
        (where, verdict) for where, verdict in sites_under(root) if verdict != PASSES_THE_READER
    ]


PLANTED_TREE = {
    "services/benchmarks.py": (
        "def section_benchmarks(session, *, section_id, scope):\n    return None\n"
    ),
    "api/reports.py": (
        "from app.services.benchmarks import section_benchmarks\n\n\n"
        "def report(session, section_id):\n"
        "    return section_benchmarks(session, section_id=section_id, scope=None)\n\n\n"
        "def forgetful(session, section_id):\n"
        "    return section_benchmarks(session, section_id=section_id)\n"
    ),
    "api/leadership.py": (
        "from app.services.benchmarks import section_benchmarks as figures_for\n\n\n"
        "def drill(session, section_id, scope):\n"
        "    return figures_for(session, section_id=section_id, scope=scope)\n\n\n"
        "def forgetful(session, section_id):\n"
        "    return figures_for(session, section_id=section_id)\n"
    ),
    "services/rollups.py": (
        "from app.services import benchmarks as bm\n\n\n"
        "def node(session, section_id):\n"
        "    return bm.section_benchmarks(session, section_id=section_id)\n\n\n"
        "def splat(session, arguments):\n"
        "    return bm.section_benchmarks(session, **arguments)\n\n\n"
        "READ = bm.section_benchmarks\n"
    ),
    "services/summary.py": (
        "def section_benchmarks_label():\n"
        "    return 'section_benchmarks'\n\n\n"
        "def read(session):\n"
        "    return section_benchmarks_label()\n"
    ),
}


def test_section_benchmarks_takes_the_reader_as_a_required_keyword() -> None:
    """`scope` is keyword-only and has no default.

    **The mutation this kills:** `scope: ActorScope | None = None` — the default
    the privacy review found, under which a leadership caller that forgets the
    reader is sealed against the instructors only. **The near miss it spares:**
    an annotation of `ActorScope | None` with no default, which is what every
    instructor caller passes `None` into.
    """
    module = importlib.import_module(THE_MODULE)
    function = getattr(module, THE_FUNCTION, None)
    assert function is not None, f"`{THE_MODULE}` exposes no `{THE_FUNCTION}`."
    parameters = inspect.signature(function).parameters
    assert (
        THE_READER in parameters
    ), f"`{THE_FUNCTION}` takes no `{THE_READER}`; E9-05 passes the reader into the seal there."
    reader = parameters[THE_READER]
    assert (
        reader.kind is inspect.Parameter.KEYWORD_ONLY
    ), f"`{THE_READER}` is {reader.kind.description}, not keyword-only."
    assert reader.default is inspect.Parameter.empty, (
        f"`{THE_READER}` defaults to {reader.default!r}. A caller that forgets the reader must "
        "fail to call, not be sealed against the instructors alone (E9-05 fix round, P2)."
    )


def test_the_sweep_flags_every_forgetful_shape_and_spares_the_explicit_calls(
    tmp_path: Path,
) -> None:
    """The control on the sweep, over a planted tree. **A red means this module is broken.**

    **The mutations this kills:** a sweep matching `ast.Name` only (the call
    through the aliased module walks free); one that does not follow an import
    alias (`figures_for(...)` walks free); one that treats a `**` call as
    passing the reader; one that looks at calls only (the stored `READ` walks
    free — `docs/MISTAKES.md` entry 53). **The near misses it spares:** both
    calls that write `scope=`, the definition itself, and a longer name called
    and spelt in a string.
    """
    for name, source in PLANTED_TREE.items():
        planted = tmp_path / name
        planted.parent.mkdir(parents=True, exist_ok=True)
        planted.write_text(source, encoding="utf-8")
    found = offenders_under(tmp_path)
    assert [where for where, _ in found] == [
        "api/leadership.py:9",
        "api/reports.py:9",
        "services/rollups.py:5",
        "services/rollups.py:9",
        "services/rollups.py:12",
    ], found
    passing = [where for where, verdict in sites_under(tmp_path) if verdict == PASSES_THE_READER]
    assert passing == ["api/leadership.py:5", "api/reports.py:5"], passing


def test_the_sweep_finds_a_call_to_section_benchmarks_in_the_real_tree() -> None:
    """The found-reference control (`docs/MISTAKES.md` entry 35).

    The rule below reports absence of a forgetful call, and a misspelt or
    renamed function has none. Every instructor report reaches the seal through
    `section_benchmarks`, so the sweep must find at least one call to it under
    `backend/app/`. **A red here means the sweep has gone blind**, not that the
    code is wrong.
    """
    assert APP_ROOT.is_dir(), f"{APP_ROOT} is not a directory, so this sweep walked nothing."
    calls = [site for site in sites_under(APP_ROOT) if site[1] != NOT_A_CALL]
    assert calls, (
        f"The sweep finds no call to `{THE_FUNCTION}` under {APP_ROOT.relative_to(REPO_ROOT)}. "
        "Either it is renamed, and this sweep's name must follow, or reports reach the seal some "
        "way this sweep cannot see."
    )


def test_every_call_to_section_benchmarks_under_backend_app_writes_scope() -> None:
    """The rule over the real tree: every call names the reader, `None` included.

    **The mutation this kills:** an instructor report, or a later leadership
    route, calling `section_benchmarks` and relying on a default for `scope`;
    a call that hands `scope` through `**`, which no reader of the call can
    check; and the function stored or passed un-called, where the eventual call
    is out of sight. **The near miss it spares:** `scope=None` written
    explicitly by an instructor caller.
    """
    offenders = offenders_under(APP_ROOT)
    assert not offenders, (
        f"These references to `{THE_FUNCTION}` do not write `{THE_READER}=` on a direct call: "
        f"{offenders}. E9-05 fix round, P2: the reader is keyword-only and required, and an "
        f"instructor's own report writes `{THE_READER}=None`."
    )


# ---------------------------------------------------------------------------
# E9-12, carried item C2: the two reader-less benchmark reads.
#
# E9-05's accepted residue: "`benchmark_trend` and `benchmark_workload` reach the
# same seal but take no reader; they pass `scope=None`. Nothing under
# `backend/app` calls either today. If E9-09's drill-down needs them for a
# leader, it gives them a required `scope` and adds them to the caller sweep;
# E9-12's invariant pass checks the sweep covers them." So: no reference to
# either under `backend/app/` outside its own definition, unless it is a direct
# call writing `scope=` — which a caller can only write once the function takes
# one. The found-reference control is the definitions themselves: both are
# required to be *defined* in `services/benchmarks.py`, so a rename cannot make
# the rule vacuous (`docs/MISTAKES.md` entry 35).
# ---------------------------------------------------------------------------

READERLESS = ("benchmark_trend", "benchmark_workload")
THE_SERVICE = Path("services/benchmarks.py")


def readerless_sites(source: str, where: str, name: str) -> list[tuple[int, str]]:
    """Every reference to `name` in one module, as (line, verdict); the device above, by name."""
    try:
        tree = ast.parse(source, filename=where)
    except SyntaxError as failure:  # pragma: no cover - a broken source tree
        pytest.fail(f"{where} does not parse ({failure}); this sweep would report it clean.")
    aliases = {name}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == name and alias.asname:
                    aliases.add(alias.asname)

    def names_it(node: ast.AST) -> bool:
        return (isinstance(node, ast.Name) and node.id in aliases) or (
            isinstance(node, ast.Attribute) and node.attr == name
        )

    called: set[int] = set()
    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and names_it(node.func):
            called.add(id(node.func))
            keywords = [keyword.arg for keyword in node.keywords]
            if THE_READER in keywords:
                verdict = PASSES_THE_READER
            elif None in keywords:
                verdict = HIDES_THE_READER
            else:
                verdict = FORGETS_THE_READER
            found.append((node.lineno, verdict))
    for node in ast.walk(tree):
        if names_it(node) and id(node) not in called:
            found.append((node.lineno, NOT_A_CALL))
    return sorted(found)


def readerless_offenders_under(root: Path) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for path in sorted(root.rglob("*.py")):
        relative = path.relative_to(root)
        source = path.read_text(encoding="utf-8")
        for name in READERLESS:
            for line, verdict in readerless_sites(source, str(relative), name):
                if verdict != PASSES_THE_READER:
                    out.append((f"{relative}:{line}", f"{name}: {verdict}"))
    return sorted(out)


READERLESS_PLANTED_TREE = {
    "services/benchmarks.py": (
        "def benchmark_trend(session, *, section_id):\n    return None\n\n\n"
        "def benchmark_workload(session, *, section_id):\n    return None\n"
    ),
    "services/reporting.py": (
        "from app.services.benchmarks import benchmark_trend as trend_for\n\n\n"
        "def leadership_report(session, section_id):\n"
        "    return trend_for(session, section_id=section_id)\n\n\n"
        "def scoped(session, section_id, scope):\n"
        "    return trend_for(session, section_id=section_id, scope=scope)\n"
    ),
    "services/rollups.py": (
        "from app.services import benchmarks as bm\n\n\n"
        "def node(session, section_id):\n"
        "    return bm.benchmark_workload(session, section_id=section_id)\n\n\n"
        "LATER = bm.benchmark_trend\n"
    ),
    "services/labels.py": "def benchmark_trend_label():\n    return 'benchmark_trend'\n",
}


def test_the_readerless_sweep_flags_calls_one_level_out_and_spares_definitions_and_scoped_calls(
    tmp_path: Path,
) -> None:
    """The control on the C2 sweep, over a planted tree. **A red means this module is broken.**

    **The mutations it kills (in the sweep):** an import alias not followed (the
    drill-down's `trend_for(...)` walks free); a module alias not followed one
    level out (`bm.benchmark_workload` walks free — entry 53); calls only (the
    stored `LATER` walks free). **The near misses it spares:** the two
    definitions, a call writing `scope=`, and a longer name.
    """
    for name, source in READERLESS_PLANTED_TREE.items():
        planted = tmp_path / name
        planted.parent.mkdir(parents=True, exist_ok=True)
        planted.write_text(source, encoding="utf-8")
    assert readerless_offenders_under(tmp_path) == [
        ("services/reporting.py:5", f"benchmark_trend: {FORGETS_THE_READER}"),
        ("services/rollups.py:5", f"benchmark_workload: {FORGETS_THE_READER}"),
        ("services/rollups.py:8", f"benchmark_trend: {NOT_A_CALL}"),
    ]


@pytest.mark.parametrize("name", READERLESS)
def test_the_readerless_benchmark_read_is_defined_in_the_benchmark_service(name: str) -> None:
    """The found-reference control: `services/benchmarks.py` defines it, so the rule below can see it.

    **A red means it was renamed or deleted**: update `READERLESS` (or, if it
    was deleted, delete its row here and say so in the pull request).
    """
    service = APP_ROOT / THE_SERVICE
    tree = ast.parse(service.read_text(encoding="utf-8"), filename=str(service))
    defined = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
    }
    assert name in defined, f"{THE_SERVICE} defines no `{name}`; it defines {sorted(defined)}."


def test_no_module_calls_a_readerless_benchmark_read_without_a_reader() -> None:
    """C2's rule over the real tree: neither read is called (or stored) without `scope=`.

    **The mutation it kills:** the drill-down (or any leadership page) calling
    `benchmark_trend` or `benchmark_workload`, which seal against the reported
    section's instructors only and would serve a leader a figure thin enough to
    subtract with her purview. **The near miss it spares:** the two definitions.
    """
    offenders = readerless_offenders_under(APP_ROOT)
    assert not offenders, (
        f"These references reach a benchmark read that takes no reader: {offenders}. E9-05's "
        "residue: give it a required `scope` and pass the reader, or do not call it."
    )
