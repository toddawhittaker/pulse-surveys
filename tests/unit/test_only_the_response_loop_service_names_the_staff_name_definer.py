"""One module names the staff-name definer, and it is `app.services.response_loop` — E7-01, done-when 6.

> A unit test proves that `services/response_loop.py` is the only module under
> `backend/app/` that names the definer.

**Why.** The definer answers names for whatever section and reader it is handed,
and every reader check sits inside it (work order decision 1). The service is the
one place the application decides which reader to pass — the session's own
person, never a value from a request. A second caller could pass any person key
it liked and read that person's sections' staff. One door keeps the reader honest.

**The rule:** under `backend/app/`, only `services/response_loop.py` may carry a
non-docstring string literal naming `section_staff_names` as a whole identifier.
The device is `test_only_the_benchmark_service_names_the_benchmark_relations.py`'s,
copied rather than shared (`docs/MISTAKES.md` entry 37): a module's syntax tree is
walked, f-string parts and implicit concatenations are joined by the parser, and
docstrings and comments are not read.

**What deliberately is not swept.** `backend/app/views_sql/section_staff_names_v001.sql`
creates the function and must name it; it is SQL, not a Python module, and the
walk reads `*.py` only. The migration is outside `backend/app/`. **Disclosed
limit** (`docs/MISTAKES.md` entry 14): a name assembled at run time is not matched.

**Controlled in both directions** (`docs/MISTAKES.md` entries 3 and 35): the
matcher against planted uses and near misses, the walk against a planted tree, and
the real service required to be *found* naming the definer. A red in a control
means this module is broken, not the code.

**Which failure a red is, before E7-01 lands.** The control on the real service:
`backend/app/services/response_loop.py` does not exist.
"""

import ast
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.invariant

REPO_ROOT = Path(__file__).resolve().parents[2]
APP_ROOT = REPO_ROOT / "backend" / "app"
THE_SERVICE = Path("services/response_loop.py")
DEFINER = "section_staff_names"
NAMED = re.compile(rf"(?<![A-Za-z0-9_]){re.escape(DEFINER)}(?![A-Za-z0-9_])")


def docstring_nodes(tree: ast.AST) -> set[int]:
    found: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            body = node.body
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                found.add(id(body[0].value))
    return found


def names_the_definer(source: str, where: str) -> bool:
    """Whether a module's non-docstring string literals name the definer."""
    try:
        tree = ast.parse(source, filename=where)
    except SyntaxError as failure:  # pragma: no cover - a broken source tree
        pytest.fail(f"{where} does not parse ({failure}); this sweep would report it clean.")
    excused = docstring_nodes(tree)
    return any(
        isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in excused
        and NAMED.search(node.value) is not None
        for node in ast.walk(tree)
    )


def offenders_under(root: Path, exempt: Path) -> list[str]:
    return sorted(
        str(path.relative_to(root))
        for path in root.rglob("*.py")
        if path.relative_to(root) != exempt
        and names_the_definer(path.read_text(encoding="utf-8"), str(path))
    )


PLANTED_OFFENDERS = {
    "planted_call.py": (
        "from sqlalchemy import text\n\n\n"
        "def names(session, section_id, reader):\n"
        "    return session.execute(text('SELECT * FROM public.section_staff_names("
        ":s, :r)'), {'s': section_id, 'r': reader})\n"
    ),
    "planted_f_string.py": (
        "def sql(schema):\n    return f'SELECT * FROM {schema}.section_staff_names(:s, :r)'\n"
    ),
    "planted_concatenation.py": (
        "SQL = (\n    'SELECT display_name '\n    'FROM section_staff_names(:s, :r)'\n)\n"
    ),
    "planted_constant.py": "FUNCTION = 'section_staff_names'\n",
}

PLANTED_NEAR_MISSES = {
    "planted_file_name.py": "SQL_FILE = 'section_staff_names_v001.sql'\n",
    "planted_prose.py": (
        '"""Names reach a student only through section_staff_names, in the service."""\n\n'
        "# section_staff_names is E7-01's definer.\n\n\n"
        "def ping():\n"
        '    """This never calls section_staff_names."""\n'
        "    return 'pong'\n"
    ),
    "planted_longer_name.py": "FLAG = 'section_staff_names_enabled'\n",
    "planted_owner.py": "OWNER = 'pulse_staff_name_definer'\n",
}

PLANTED_TREE = {
    "services/response_loop.py": "SQL = 'SELECT * FROM public.section_staff_names(:s, :r)'\n",
    "services/survey_read.py": "SQL = 'SELECT display_name FROM section_staff_names(:s, :r)'\n",
    "api/student.py": "NAMES = 'section_staff_names'\n",
    "views_sql/__init__.py": "FILES = ('section_staff_names_v001.sql',)\n",
    "services/authz.py": '"""The staff check also lives in section_staff_names."""\n',
}


def test_the_matcher_finds_the_definer_the_service_really_names() -> None:
    """The control on the sweep: the service, which calls the definer, is found naming it.

    **A red here means this module is broken** — or the service does not exist yet,
    which is the red this module carries before E7-01 lands.
    """
    service = APP_ROOT / THE_SERVICE
    assert service.is_file(), (
        f"{service.relative_to(REPO_ROOT)} does not exist. E7-01 owns it, with 'the one Python "
        "call to the definer'."
    )
    assert names_the_definer(service.read_text(encoding="utf-8"), str(service)), (
        f"The matcher finds no `{DEFINER}` in {service.relative_to(REPO_ROOT)}, which calls it; "
        "it can therefore see nothing, and the sweep below passes over every module."
    )


def test_the_matcher_flags_planted_uses_and_spares_its_near_misses(tmp_path: Path) -> None:
    """The instrument, both directions. **A red means this module is broken.**

    **The mutations this kills:** a plain substring search (flags the file name,
    the longer flag and the owner role), whole-string equality (spares the call,
    the f-string and the concatenation), and the docstring exemption dropped.
    """
    for name, source in {**PLANTED_OFFENDERS, **PLANTED_NEAR_MISSES}.items():
        (tmp_path / name).write_text(source, encoding="utf-8")
    flagged = {
        path.name
        for path in tmp_path.glob("*.py")
        if names_the_definer(path.read_text(encoding="utf-8"), str(path))
    }
    assert flagged == set(
        PLANTED_OFFENDERS
    ), f"The matcher flagged {sorted(flagged)}; the planted uses are {sorted(PLANTED_OFFENDERS)}."


def test_the_walk_reaches_every_directory_and_spares_only_the_service(tmp_path: Path) -> None:
    """The control on the walk. **A red means this module is broken.**

    **The mutations this kills:** the walk narrowed to one directory, and the
    exemption written as `services/`, under which `services/survey_read.py` — the
    likeliest second caller — walks free.
    """
    for name, source in PLANTED_TREE.items():
        planted = tmp_path / name
        planted.parent.mkdir(parents=True, exist_ok=True)
        planted.write_text(source, encoding="utf-8")
    assert offenders_under(tmp_path, THE_SERVICE) == ["api/student.py", "services/survey_read.py"]


def test_no_module_but_the_response_loop_service_names_the_staff_name_definer() -> None:
    """The rule: only `app/services/response_loop.py` names `section_staff_names`.

    **The mutation this kills:** `services/survey_read.py` (or a route) calling the
    definer itself to fill the payload, with a reader of its own choosing.

    **The non-emptiness control:** the package holds more than the one exempt
    module.
    """
    assert APP_ROOT.is_dir(), f"{APP_ROOT} is not a directory, so this sweep walked nothing."
    swept = [path for path in APP_ROOT.rglob("*.py") if path.relative_to(APP_ROOT) != THE_SERVICE]
    assert len(swept) > 1, f"{APP_ROOT} holds next to nothing beyond {THE_SERVICE}."
    offenders = offenders_under(APP_ROOT, THE_SERVICE)
    assert not offenders, (
        f"These modules under backend/app name `{DEFINER}`, which only `{THE_SERVICE}` may do: "
        f"{offenders}. E7-01 done-when 6: one door. Route the read through "
        "`app.services.response_loop.section_staff_names`."
    )
