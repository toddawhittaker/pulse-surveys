"""Every leadership caller of the staff-name door passes a scope — E9-12, carried item C3 (ADR 0201).

**Why.** README ruling 3: the staff-name definer answers any live leadership
holder, and "the Python door passes only sections from the reader's resolved
purview". The door is `app.services.response_loop.section_staff_names(session, *,
section_ids, reader_user_id=None, reader_person_id=None, scope)`; given a
leadership scope it narrows `section_ids` to the scope's purview before the
definer is called (E9-03's settlement), and `scope` is a required keyword (E9-03's
fix round). So a leadership page that calls it with `scope=None` hands the
definer whatever list it built — which, for chair and above, the database answers
whatever it holds (decision 16). Done-when 8 asserts the ids the definer received
at run time; this sweep holds the call sites.

**The rule, under `backend/app/`:**

  - every call to the door writes `scope=` as a keyword — never relies on a
    default, never hands it through `**`, and the door is never stored or
    passed un-called (what calls it later is out of sight);
  - every call made from a **leadership page** — a module in
    `LEADERSHIP_PAGE_MODULES`, or a function anywhere whose name says
    `leadership` — writes a scope that is not the literal `None`. An instructor's
    or a student's own page may write `scope=None`; that is the near miss.

**The device** is the E9-05 sweep's (`test_every_section_benchmarks_caller_names_
the_reader.py`): calls read off the syntax tree, an import alias followed, an
attribute call through any module alias matched by its attribute name. The
definer's own SQL string (`public.section_staff_names(`) is a string, not a
reference, and is not matched here — `test_only_the_response_loop_service_names_
the_staff_name_definer.py` owns that one.

**Controlled in both directions** (`docs/MISTAKES.md` entries 3, 35 and 53): a
planted tree with a forgetful call, a `**` call, a stored reference, a leadership
call writing `scope=None` through an import alias and another through a module
alias one level out, beside the allowed shapes; and the real roll-up service
required to be *found* calling the door with a scope. **Disclosed limit** (entry
14): a name assembled at run time is not matched; nothing outside `backend/app/`
is read; a leadership page in a module not listed and in a function not named for
leadership is held only to the first clause.

**Marked `invariant`. Expected green on today's branch.**

**Extended by E9-14 (item 4) to the lead-name door.**
`app.services.response_loop.section_lead_name` reads the Lead Faculty name
through the same definer, and the E9 boundary privacy review found its `scope`
defaulting to `None`. E9-14 makes it a required keyword
(`test_the_lead_name_door_takes_a_scope_with_no_default.py`), and the same
rule now holds its call sites: every call writes `scope=`, and a leadership
page's is not the literal `None`. Both doors are swept by the one rule, each
with its own planted control and its own found-reference control (the
drill-down asks the lead's name with the reader's scope, ADR 0206). **Expected
red before E9-14 lands** wherever a caller of the lead-name door relies on the
default (`FORGETS_THE_SCOPE`).
"""

import ast
from pathlib import Path

import pytest

pytestmark = pytest.mark.invariant

REPO_ROOT = Path(__file__).resolve().parents[2]
APP_ROOT = REPO_ROOT / "backend" / "app"
THE_DOOR = "section_staff_names"
# E9-14 item 4: the lead-name door, held to the same rule.
THE_LEAD_DOOR = "section_lead_name"
SWEPT_DOORS = (THE_DOOR, THE_LEAD_DOOR)
THE_DOORS_MODULE = Path("services/response_loop.py")
THE_READER = "scope"
LEADERSHIP_PAGE_MODULES = (Path("services/rollups.py"), Path("api/leadership.py"))
THE_ROLLUP_SERVICE = Path("services/rollups.py")

PASSES_A_SCOPE = "passes a scope"
PASSES_NONE = "passes scope=None"
FORGETS_THE_SCOPE = "a call without scope="
HIDES_THE_SCOPE = "a call through ** the sweep cannot read"
NOT_A_CALL = "a reference that is not a call"


def call_sites(
    source: str, where: str, door: str = THE_DOOR
) -> list[tuple[int, str, tuple[str, ...]]]:
    """Every reference to `door` in one module: (line, verdict, enclosing function names)."""
    try:
        tree = ast.parse(source, filename=where)
    except SyntaxError as failure:  # pragma: no cover - a broken source tree
        pytest.fail(f"{where} does not parse ({failure}); this sweep would report it clean.")
    aliases = {door}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == door and alias.asname:
                    aliases.add(alias.asname)

    def names_it(node: ast.AST) -> bool:
        return (isinstance(node, ast.Name) and node.id in aliases) or (
            isinstance(node, ast.Attribute) and node.attr == door
        )

    found: list[tuple[int, str, tuple[str, ...]]] = []
    called: set[int] = set()

    def visit(node: ast.AST, enclosing: tuple[str, ...]) -> None:
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            enclosing = (*enclosing, node.name)
        if isinstance(node, ast.Call) and names_it(node.func):
            called.add(id(node.func))
            keywords = {keyword.arg: keyword.value for keyword in node.keywords}
            if THE_READER in keywords:
                value = keywords[THE_READER]
                is_none = isinstance(value, ast.Constant) and value.value is None
                verdict = PASSES_NONE if is_none else PASSES_A_SCOPE
            elif None in keywords:
                verdict = HIDES_THE_SCOPE
            else:
                verdict = FORGETS_THE_SCOPE
            found.append((node.lineno, verdict, enclosing))
        elif names_it(node) and id(node) not in called:
            found.append((node.lineno, NOT_A_CALL, enclosing))
        for child in ast.iter_child_nodes(node):
            visit(child, enclosing)

    visit(tree, ())
    return sorted(found)


def is_a_leadership_page(relative: Path, enclosing: tuple[str, ...]) -> bool:
    return relative in LEADERSHIP_PAGE_MODULES or any(
        "leadership" in name.lower() for name in enclosing
    )


def offenders_under(root: Path, door: str = THE_DOOR) -> list[tuple[str, str]]:
    """Every reference to `door` under `root` the rule forbids, as ("path:line", verdict)."""
    out: list[tuple[str, str]] = []
    for path in sorted(root.rglob("*.py")):
        relative = path.relative_to(root)
        source = path.read_text(encoding="utf-8")
        for line, verdict, enclosing in call_sites(source, str(relative), door):
            if verdict == PASSES_A_SCOPE:
                continue
            if verdict == PASSES_NONE and not is_a_leadership_page(relative, enclosing):
                continue
            out.append((f"{relative}:{line}", verdict))
    return out


PLANTED_TREE = {
    "services/response_loop.py": (
        "def section_staff_names(session, *, section_ids, scope):\n"
        "    return []\n\n\n"
        "def student_header(session, section_id):\n"
        "    return section_staff_names(session, section_ids=[section_id], scope=None)\n"
    ),
    "services/rollups.py": (
        "from app.services.response_loop import section_staff_names as names_for\n\n\n"
        "def tree(session, sections, scope):\n"
        "    return names_for(session, section_ids=sections, scope=scope)\n\n\n"
        "def careless(session, sections):\n"
        "    return names_for(session, section_ids=sections, scope=None)\n"
    ),
    "services/reporting.py": (
        "from app.services import response_loop as loop\n\n\n"
        "def instructor_report(session, section_id):\n"
        "    return loop.section_staff_names(session, section_ids=[section_id], scope=None)\n\n\n"
        "def leadership_report(session, section_id):\n"
        "    return loop.section_staff_names(session, section_ids=[section_id], scope=None)\n\n\n"
        "def forgetful(session, section_id):\n"
        "    return loop.section_staff_names(session, section_ids=[section_id])\n\n\n"
        "def splat(session, arguments):\n"
        "    return loop.section_staff_names(session, **arguments)\n\n\n"
        "LATER = loop.section_staff_names\n"
    ),
    "services/labels.py": (
        "def section_staff_names_label():\n" "    return 'section_staff_names'\n"
    ),
}


def test_the_sweep_flags_every_careless_shape_and_spares_the_scoped_and_own_page_calls(
    tmp_path: Path,
) -> None:
    """The control on the sweep, over a planted tree. **A red means this module is broken.**

    **The mutations it kills (in the sweep):** an import alias not followed (the
    roll-up's `names_for(..., scope=None)` walks free); a module alias not
    followed one level out (`loop.section_staff_names` in `leadership_report`
    walks free — `docs/MISTAKES.md` entry 53); `scope=None` treated as a scope;
    calls only, so the stored `LATER` walks free; a `**` call read as passing a
    scope. **The near misses it spares:** the student header and the instructor
    report writing `scope=None`, the roll-up passing its scope, and a longer name
    called and spelt in a string.
    """
    for name, source in PLANTED_TREE.items():
        planted = tmp_path / name
        planted.parent.mkdir(parents=True, exist_ok=True)
        planted.write_text(source, encoding="utf-8")
    found = offenders_under(tmp_path)
    assert found == [
        ("services/reporting.py:9", PASSES_NONE),
        ("services/reporting.py:13", FORGETS_THE_SCOPE),
        ("services/reporting.py:17", HIDES_THE_SCOPE),
        ("services/reporting.py:20", NOT_A_CALL),
        ("services/rollups.py:9", PASSES_NONE),
    ], found


def test_the_roll_up_service_is_found_calling_the_door_with_a_scope() -> None:
    """The found-reference control (`docs/MISTAKES.md` entry 35).

    E9-07's tree names every staff member through this door in one call. A sweep
    that finds no scoped call there has gone blind (a renamed door, an alias it
    cannot follow), and the rule below would report a clean tree it did not read.
    """
    service = APP_ROOT / THE_ROLLUP_SERVICE
    assert service.is_file(), f"{service.relative_to(REPO_ROOT)} does not exist."
    sites = call_sites(service.read_text(encoding="utf-8"), str(service))
    assert any(verdict == PASSES_A_SCOPE for _line, verdict, _where in sites), (
        f"The sweep finds no call to `{THE_DOOR}` passing a scope in "
        f"{service.relative_to(REPO_ROOT)}; it finds {sites}."
    )


def test_every_leadership_caller_of_the_staff_name_door_passes_a_scope() -> None:
    """The rule over the real tree.

    **The mutation it kills:** a leadership page calling the door with
    `scope=None` (or without a scope, or through `**`), which hands the definer
    the page's whole section list for chair and above. **The near miss it
    spares:** an instructor's or a student's own page writing `scope=None`.
    """
    assert APP_ROOT.is_dir(), f"{APP_ROOT} is not a directory, so this sweep walked nothing."
    door = APP_ROOT / THE_DOORS_MODULE
    assert door.is_file(), f"{door.relative_to(REPO_ROOT)} does not exist; the door lives there."
    offenders = offenders_under(APP_ROOT)
    assert not offenders, (
        f"These references to `{THE_DOOR}` break the rule: {offenders}. README ruling 3: the door "
        "passes only sections from the reader's resolved purview, which it can do only when a "
        "leadership page hands it the reader's scope."
    )


# ---------------------------------------------------------------------------
# E9-14 item 4: the lead-name door, under the same rule.
# ---------------------------------------------------------------------------

PLANTED_LEAD_TREE = {
    "services/response_loop.py": (
        "def section_lead_name(session, *, section_id, scope, reader_user_id=None):\n"
        "    return None\n\n\n"
        "def student_page(session, section_id, user_id):\n"
        "    return section_lead_name(\n"
        "        session, section_id=section_id, scope=None, reader_user_id=user_id\n"
        "    )\n"
    ),
    "services/reporting.py": (
        "from app.services import response_loop as loop\n"
        "from app.services.response_loop import section_lead_name as lead_of\n\n\n"
        "def instructor_report(session, section_id, person_id):\n"
        "    return loop.section_lead_name(session, section_id=section_id, scope=None)\n\n\n"
        "def leadership_report(session, section_id, leader):\n"
        "    return lead_of(session, section_id=section_id, scope=leader)\n\n\n"
        "def leadership_careless(session, section_id):\n"
        "    return loop.section_lead_name(session, section_id=section_id, scope=None)\n\n\n"
        "def forgetful(session, section_id):\n"
        "    return lead_of(session, section_id=section_id)\n\n\n"
        "def section_lead_name_label():\n"
        "    return 'section_lead_name'\n"
    ),
}


def test_the_sweep_flags_every_careless_call_of_the_lead_name_door(tmp_path: Path) -> None:
    """The control on the sweep for the second door, over a planted tree. **A red means this module is broken.**

    **The mutations it kills (in the sweep):** the door's name not threaded
    through (the planted lead-door calls are not found at all); an import alias
    of the lead door not followed (`lead_of(...)` without a scope walks free);
    `scope=None` on a leadership page not caught one level out
    (`loop.section_lead_name` in `leadership_careless`). **The near misses it
    spares:** the student's and the instructor's pages writing `scope=None`, the
    leadership report passing its reader, and a longer name spelt in a string.
    """
    for name, source in PLANTED_LEAD_TREE.items():
        planted = tmp_path / name
        planted.parent.mkdir(parents=True, exist_ok=True)
        planted.write_text(source, encoding="utf-8")
    found = offenders_under(tmp_path, THE_LEAD_DOOR)
    assert found == [
        ("services/reporting.py:14", PASSES_NONE),
        ("services/reporting.py:18", FORGETS_THE_SCOPE),
    ], found


def test_a_call_of_the_lead_name_door_passing_a_scope_is_found_in_the_application() -> None:
    """The found-reference control for the second door (`docs/MISTAKES.md` entry 35).

    ADR 0206: the drill-down asks the Lead Faculty name with the reader's scope,
    so at least one call under `backend/app/` passes a scope that is not the
    literal `None`. A sweep that finds none has gone blind to this door (a
    renamed door, an alias it cannot follow), and the rule below would report a
    clean tree it did not read.
    """
    found = [
        (str(path.relative_to(APP_ROOT)), line)
        for path in sorted(APP_ROOT.rglob("*.py"))
        for line, verdict, _where in call_sites(
            path.read_text(encoding="utf-8"), str(path), THE_LEAD_DOOR
        )
        if verdict == PASSES_A_SCOPE
    ]
    assert found, (
        f"The sweep finds no call to `{THE_LEAD_DOOR}` passing a scope anywhere under "
        f"{APP_ROOT.relative_to(REPO_ROOT)}; the drill-down makes one (ADR 0206)."
    )


def test_every_caller_of_the_lead_name_door_writes_its_scope_and_a_leadership_page_a_real_one() -> (
    None
):
    """The rule over the real tree, for `section_lead_name`.

    **The mutation it kills:** a caller relying on the old `scope=None` default
    (red before E9-14 wherever one does); a leadership page passing
    `scope=None`, which reads a lead's name for a section outside the reader's
    purview. **The near miss it spares:** an instructor's or a student's own
    page writing `scope=None` explicitly.
    """
    assert APP_ROOT.is_dir(), f"{APP_ROOT} is not a directory, so this sweep walked nothing."
    offenders = offenders_under(APP_ROOT, THE_LEAD_DOOR)
    assert not offenders, (
        f"These references to `{THE_LEAD_DOOR}` break the rule: {offenders}. E9-14: the door's "
        "scope is a required keyword, and a leadership page hands it the reader's scope."
    )
