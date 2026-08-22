"""The three org views are reached through the grant and nowhere else — ticket E0-41.

`pulse_app` holds an **unfiltered** `SELECT` on `lead_faculty_course`,
`assignment_scope` and `containment_path`. Nothing in the database narrows them:
the only narrowing anywhere is the `WHERE` inside the grant functions in
`backend/app/services/authz.py`, which is where SPEC §2.1's purview rules live —
"a Lead Faculty assignment never grants sibling leads' courses" (§4.1 item 2)
among them. A module that runs its own `SELECT` against one of those views reads
the institution, and every rule §2.1 states about scope is a rule that query does
not apply.

**Until this file, that was a reviewer's grep.** `backend/app/services/authz.py`
calls the one-import property a control; a property nothing executes is a
comment (`docs/MISTAKES.md` entry 9). So the two halves are mechanised here:

  - no module under `backend/app/` outside the grant chokepoint runs SQL naming
    one of the org views;
  - no module under `backend/app/` outside it imports `app.views_sql.queries`,
    the module that holds those statements.

Neither implies the other. The first catches a query somebody writes fresh in a
service; the second catches the shorter route — importing the statements that
already exist and running them on a session of the caller's own, which names no
view in the importing module at all.

**Two modules are exempt, and the second exemption is what makes the first half
readable.** `services/authz.py` is the chokepoint the rule is written around.
Everything under `backend/app/views_sql/` is where the SQL itself lives (ADR
0041: "the SQL lives in `backend/app/views_sql/<object>_v<NNN>.sql`, and the
revision executes it by name"), and `app.views_sql.queries` is the module the
second half keeps to one importer — a rule that forbade the query module from
naming the views it queries would forbid the design the ticket is describing.

**The inventory of view names comes from the directory**, not from a list in this
file: the `.sql` files under `backend/app/views_sql/` are read at test time and
every view they create is collected. The three names below are then asserted to
be *in* that inventory, which is the premise rather than the inventory — a view
renamed, or a file moved out of the directory, fails loudly here instead of
leaving a sweep that searches for a string nothing defines.

**Read out of the syntax tree, not out of the file text**, for the reason
`tests/unit/test_no_service_reads_an_identity_table_directly.py` gives: a correct
module is very likely to *say* `assignment_scope` in a docstring, because "this
goes through the grant rather than reading `assignment_scope`" is the sentence a
careful implementer writes next to the call. Searching the text would turn that
sentence into a failure and teach the next person to delete the comment. So
comments are absent from the tree entirely, and docstrings are subtracted by name.

**What this cannot see**, stated so nothing here is cited as more than it is
(`docs/MISTAKES.md` entry 14):

  - **A view added later is not swept by the first half.** The rule polices the
    three views the ticket names. The directory also holds E0-10's
    identity-separated read views, which read paths are *supposed* to name, and
    no record says how to tell a grant-only view from a read view — so a fourth
    org view has to be added to `ORG_VIEWS` below by the ticket that ships it.
    The second half needs no such edit: it is about the query module, whatever
    that module comes to hold.
  - **A relation name assembled at run time**, and a read that reaches the views
    through a helper in a package this sweep does not walk.
  - **`from app import views_sql` followed by attribute access.** The import half
    matches an import that names the `queries` module; reaching the package and
    walking to it is a route this does not follow, and closing it would mean
    flagging every legitimate use of the package's directory.
  - **Migrations.** `backend/alembic.ini`'s revisions live outside
    `backend/app/`, and creating these views is exactly what they are for.
"""

import ast
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.invariant

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = REPO_ROOT / "backend"
APP_ROOT = BACKEND_ROOT / "app"
VIEWS_SQL_DIR = APP_ROOT / "views_sql"
AUTHZ_MODULE = APP_ROOT / "services" / "authz.py"

# The module that holds the statements the grant functions run, spelled as the
# ticket spells it and as an import would.
QUERY_MODULE = "app.views_sql.queries"

# The three views E0-41 names, and the reason each is a view rather than a table
# somebody could be granted less of: SPEC §2.1's supervision graph and purview
# rules are computed over them. **This is a premise, not the inventory** — the
# inventory is read out of `views_sql/` at test time, and these three are asserted
# to be in it, so a rename fails here rather than silently emptying the sweep.
ORG_VIEWS = ("lead_faculty_course", "assignment_scope", "containment_path")


# The modules the rule is written around. `services/authz.py` is the chokepoint;
# `views_sql/` is where the SQL lives, and exempting it is what leaves the second
# half — one importer of `queries` — with something to say.
def is_exempt(path: Path) -> bool:
    """Whether `path` is one of the two places the org views may be named."""
    return path == AUTHZ_MODULE or VIEWS_SQL_DIR in path.parents


# **Every modifier Postgres allows between `CREATE` and `VIEW`.** Measured during
# E0-34's review against every spelling the server accepts:
# `tests/integration/test_identity_separated_views.py::CREATES_A_VIEW` is the same
# pattern, and it is here rather than imported because a test module importing its
# sibling depends on where pytest put `tests/` on `sys.path` and an import error
# is not a red. A file this misses is a view that drops out of the inventory
# below, which is the failure the guard test exists to catch.
CREATES_A_VIEW = re.compile(
    r"\bcreate\s+(?:or\s+replace\s+)?"
    r"(?:(?:temp(?:orary)?|materialized|recursive)\s+)*view\s+"
    r"(?:if\s+not\s+exists\s+)?"
    r'(?:"?\w+"?\s*\.\s*)?"?(?P<name>\w+)"?',
    re.IGNORECASE,
)

# A relation reference in SQL: the name in the position a statement reads or
# writes it from, optionally schema-qualified and optionally quoted. The keyword
# is what keeps a column called `assignment_scope_id` out, and what keeps a
# `GRANT … ON public.assignment_scope` from reading as a query.
RELATION_KEYWORDS = r"\b(?:from|join|into|update|delete\s+from|table)"


def reference_to(names: tuple[str, ...]) -> re.Pattern[str]:
    """A pattern matching any of `names` in the position a statement reads it from."""
    return re.compile(
        RELATION_KEYWORDS + r"\s+(?:public\s*\.\s*)?\"?(" + "|".join(names) + r")\"?\b",
        re.IGNORECASE,
    )


def views_created_under_views_sql() -> set[str]:
    """Every view the `.sql` files in `views_sql/` create, by name.

    The inventory, read from the directory at test time. A new org view lands with
    its own `.sql` file under ADR 0041's rule, so it appears here without this
    file being edited — which is the difference between an inventory and a list
    somebody has to remember to update.
    """
    files = sorted(VIEWS_SQL_DIR.glob("*.sql"))
    assert files, (
        f"There are no `.sql` files under {VIEWS_SQL_DIR.relative_to(REPO_ROOT)}, so the view "
        "inventory this file sweeps for is empty and every assertion below is vacuous. ADR 0041 "
        "puts every view's SQL there and E0-10 shipped the first of them."
    )
    return {
        match.group("name").lower()
        for path in files
        for match in CREATES_A_VIEW.finditer(path.read_text(encoding="utf-8"))
    }


def parsed_modules() -> dict[Path, ast.Module]:
    """Every module under `backend/app/` that is not exempt, parsed.

    A file that does not parse is a failure of the sweep rather than a module to
    skip: it would drop silently out of both halves below, and the half that
    matters is the one reporting what it did *not* find.
    """
    found: dict[Path, ast.Module] = {}
    for path in sorted(APP_ROOT.rglob("*.py")):
        if is_exempt(path):
            continue
        source = path.read_text(encoding="utf-8")
        try:
            found[path] = ast.parse(source, filename=str(path))
        except SyntaxError as failure:  # pragma: no cover - a broken source tree
            pytest.fail(
                f"{path.relative_to(REPO_ROOT)} does not parse ({failure}), so this sweep cannot "
                "read it and would report success having skipped it."
            )
    return found


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


def executable_strings(tree: ast.AST) -> list[str]:
    """Every string constant in a module that is not a docstring."""
    excluded = docstring_constants(tree)
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in excluded
    ]


def package_of(path: Path) -> str:
    """The dotted package a module sits in, as an import inside `backend/` sees it.

    `backend/app/services/safety.py` sits in `app.services`; so does
    `backend/app/services/__init__.py`, whose own module name *is* that package.
    Needed because a relative import resolves against the package rather than
    against the file, and a sweep that read only absolute imports is defeated by
    `from ..views_sql import queries` — one level out, which is where a closed-set
    guard is usually defeated.
    """
    parts = path.relative_to(BACKEND_ROOT).with_suffix("").parts
    return ".".join(parts[:-1])


def imported_targets(tree: ast.AST, path: Path) -> set[str]:
    """Every dotted module name a module imports, relative imports resolved."""
    package = package_of(path)
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                anchor = package.split(".") if package else []
                climbed = anchor[: len(anchor) - (node.level - 1)]
                if not climbed:
                    # More dots than there are packages to climb. Python refuses
                    # such an import outright, so there is nothing to resolve and
                    # nothing this sweep could attribute it to.
                    continue
                prefix = ".".join(climbed)
                base = f"{prefix}.{base}" if base else prefix
            if base:
                found.add(base)
                found |= {f"{base}.{alias.name}" for alias in node.names}
    return found


# Samples the sweeps are run against before they are believed, built from a view
# the inventory really holds rather than from a name written here. A pattern
# searched against text is a test that can go blind and report success
# (`docs/MISTAKES.md` entry 3), and the allow half is where the weight is: a
# purview query is written over columns — `person_id`, `course_id` — and a sweep
# that fired on a column named after a view, or on a `GRANT` naming one, would be
# red against a correct implementation and would be deleted rather than fixed.
def sql_must_catch(view: str) -> tuple[str, ...]:
    """SQL that reads one of the org views, in the shapes a module would write it."""
    return (
        f"SELECT * FROM {view} WHERE person_id = :person_id",  # noqa: S608
        f'SELECT 1 FROM public."{view}"',  # noqa: S608
        f"SELECT 1 FROM course JOIN {view} ON true",  # noqa: S608
        f"select 1 from PUBLIC . {view.upper()}",  # noqa: S608
        f"UPDATE {view} SET course_id = :course_id",  # noqa: S608
    )


def sql_must_allow(view: str) -> tuple[str, ...]:
    """Text that names an org view without reading one, and text that names none."""
    return (
        f"SELECT * FROM {view}_totals",  # noqa: S608
        f"SELECT {view}_id FROM role_assignment WHERE person_id = :person_id",  # noqa: S608
        f"GRANT SELECT ON public.{view} TO pulse_app",
        f"-- {view} is reached through the grant functions in `services/authz.py`",
        "SELECT role, person_id FROM role_assignment WHERE person_id = :person_id",
    )


IMPORTS_MUST_CATCH = (
    ("app/api/reports.py", f"import {QUERY_MODULE}"),
    ("app/api/reports.py", f"from {QUERY_MODULE} import LEAD_FACULTY_COURSES"),
    ("app/api/reports.py", "from app.views_sql import queries"),
    ("app/services/reporting.py", "from ..views_sql import queries"),
    ("app/services/reporting.py", "from ..views_sql.queries import LEAD_FACULTY_COURSES"),
    ("app/api/v1/reports.py", "from ...views_sql import queries"),
)

IMPORTS_MUST_ALLOW = (
    ("app/api/reports.py", "from app.services import authz"),
    ("app/api/reports.py", "from app.services.authz import resolve_scope"),
    ("app/services/reporting.py", "from . import authz"),
    ("app/services/reporting.py", "from ..models import Course"),
    ("app/api/reports.py", "import app.views_sql.loader"),
)


def test_the_sweeps_in_this_file_catch_what_they_claim_to_and_allow_what_they_must() -> None:
    """Both matchers, run against both directions, before either is believed.

    `docs/MISTAKES.md` entry 3's rule for a pattern searched against text: run it
    against the text you claim it catches *and* against the text you claim it
    allows. The import half needs the same treatment for a different reason —
    **the relative forms are where a closed-set guard gets defeated one level
    out**. `from ..views_sql import queries` names no module this file could match
    literally, and a sweep that read `ast.ImportFrom.module` alone would report a
    clean tree over a module that imports the statements and runs them itself.

    The samples are built from a view the inventory really holds, so this cannot
    pass by matching a name nothing defines.
    """
    inventory = views_created_under_views_sql()
    policed = tuple(sorted(name for name in ORG_VIEWS if name in inventory))
    assert policed, (
        f"None of {list(ORG_VIEWS)} is created by any `.sql` file under "
        f"{VIEWS_SQL_DIR.relative_to(REPO_ROOT)} (it creates {sorted(inventory)}), so there is no "
        "real view name to build a sample from. The next test diagnoses that."
    )
    pattern = reference_to(policed)
    view = policed[0]

    for sample in sql_must_catch(view):
        assert pattern.search(sample), (
            f"The relation sweep found no org view in {sample!r}, which names {view!r} in the "
            "position a statement reads it from. A sweep that has gone blind reads exactly like a "
            "sweep that found nothing wrong."
        )
    for sample in sql_must_allow(view):
        found = pattern.search(sample)
        read = found.group(0) if found else ""
        assert not found, (
            f"The relation sweep read {read!r} out of {sample!r}, which reads no org "
            "view. A grant, a column named after a view, a differently-named relation and a "
            "comment all have to pass, or this sweep is red against the code it is meant to allow."
        )

    for where, sample in IMPORTS_MUST_CATCH:
        targets = imported_targets(ast.parse(sample), BACKEND_ROOT / where)
        assert QUERY_MODULE in targets, (
            f"`{sample}` in `{where}` resolved to {sorted(targets)}, which does not include "
            f"`{QUERY_MODULE}`. That import reaches the statements the grant functions run, and "
            "the sweep below would report the module clean."
        )
    for where, sample in IMPORTS_MUST_ALLOW:
        targets = imported_targets(ast.parse(sample), BACKEND_ROOT / where)
        assert QUERY_MODULE not in targets, (
            f"`{sample}` in `{where}` resolved to {sorted(targets)}, which includes "
            f"`{QUERY_MODULE}` and should not. A sweep that flags an ordinary import is one "
            "somebody deletes rather than fixes."
        )


def test_the_three_org_views_are_created_by_a_file_in_the_views_sql_directory() -> None:
    """The premise the SQL half rests on, asserted rather than assumed.

    The names this sweep polices have to be names something defines, or the sweep
    is a search for a string that appears nowhere and its silence means nothing —
    `docs/MISTAKES.md` entry 3 in the shape that is hardest to see, because a
    sweep looking for the wrong word passes every run.

    The inventory is read out of `views_sql/` rather than written here, so a view
    renamed by a later ticket fails here — where the message says which name went
    missing — instead of quietly reducing the sweep to nothing.
    """
    inventory = views_created_under_views_sql()

    missing = sorted(name for name in ORG_VIEWS if name not in inventory)
    assert not missing, (
        f"{missing} are not created by any `.sql` file under "
        f"{VIEWS_SQL_DIR.relative_to(REPO_ROOT)}, which creates {sorted(inventory)}. E0-41's "
        "finding is about these three views: `pulse_app` holds unfiltered `SELECT` on them and "
        "the only narrowing is the `WHERE` inside `services/authz.py`. If one has been renamed, "
        "rename it in `ORG_VIEWS` in this file in the same change; if one has been dropped, the "
        "rule about it goes with it. A sweep for a name nothing defines is green forever."
    )


def test_no_module_outside_the_grant_chokepoint_runs_sql_naming_an_org_view() -> None:
    """The criterion, over the SQL every other module under `backend/app/` carries.

    SPEC §2.1 puts the purview rules — the supervision graph, the own grant, and
    §4.1 item 2's "a Lead Faculty assignment never grants sibling leads' courses"
    — in the `WHERE` clauses of the grant functions. The views themselves are
    unfiltered and `pulse_app` may read all of them, so a second query written
    anywhere else is a purview computed by whoever wrote it.

    **The mutation this exists to survive:** a service module gaining a direct
    `SELECT … FROM lead_faculty_course` — which is not a careless thing to write.
    It is the shortest way to answer "which courses does this lead have", the
    view is right there, and the query works perfectly for the person who tests it
    with their own id.

    **The near miss that must stay green:** naming a view in a docstring or a
    comment, which is what a module that deliberately goes through the grant is
    expected to do.
    """
    inventory = views_created_under_views_sql()
    policed = tuple(sorted(name for name in ORG_VIEWS if name in inventory))
    assert policed, (
        "No org view this file polices is created under `views_sql/`; "
        "`test_the_three_org_views_are_created_by_a_file_in_the_views_sql_directory` diagnoses it."
    )
    pattern = reference_to(policed)

    modules = parsed_modules()
    assert modules, (
        f"There are no Python modules under {APP_ROOT.relative_to(REPO_ROOT)} outside the exempt "
        "ones, so this sweep looked at nothing and would report success. SPEC §13 puts the real "
        "application there."
    )
    assert AUTHZ_MODULE.is_file(), (
        f"{AUTHZ_MODULE.relative_to(REPO_ROOT)} does not exist, so the chokepoint this rule is "
        "written around is not there and 'every module except that one' is every module. E0-11 "
        "ships it and SPEC §2.1's purview rules live in it."
    )

    naming = {
        str(path.relative_to(REPO_ROOT)): sorted(
            {
                match.group(1).lower()
                for statement in executable_strings(tree)
                for match in pattern.finditer(statement)
            }
        )
        for path, tree in modules.items()
    }
    offenders = {path: found for path, found in naming.items() if found}
    assert not offenders, (
        f"{offenders} run SQL naming an org view. `pulse_app` holds an unfiltered `SELECT` on "
        f"{list(policed)} — no grant narrows them and no view filters itself — so the only thing "
        "between a caller and the whole institution is the `WHERE` clause inside "
        "`backend/app/services/authz.py`'s grant functions, where SPEC §2.1's purview rules and "
        "§4.1 item 2's sibling-isolation rule are written.\n"
        "A query written anywhere else applies whichever of those rules its author remembered. If "
        "a read path genuinely needs one of these views, it goes through the grant function that "
        "already narrows it; if a new grant function is needed, it belongs in `authz.py` beside "
        "the others, which is what makes this rule one file to review."
    )


def test_no_module_outside_the_grant_chokepoint_imports_the_view_query_module() -> None:
    """The other route to the same rows, which names no view in the importing module.

    `backend/app/services/authz.py` calls this property a control. It was one only
    as long as somebody grepped for it: importing `app.views_sql.queries` and
    running one of its statements on a session of your own reaches exactly the
    unfiltered views the test above is about, and the module doing it contains no
    SQL for that sweep to read.

    **The mutation this exists to survive:** a module outside `authz.py` importing
    `queries` — by any of the forms `imported_targets` resolves, including the
    relative ones, since `from ..views_sql import queries` is what somebody inside
    `services/` would naturally write.

    **The near miss that must stay green:** importing `app.services.authz` itself,
    which is the sanctioned way to reach these rows and must not be flagged.
    """
    modules = parsed_modules()
    assert modules, (
        f"There are no Python modules under {APP_ROOT.relative_to(REPO_ROOT)} outside the exempt "
        "ones, so this sweep looked at nothing and would report success."
    )

    importers = sorted(
        str(path.relative_to(REPO_ROOT))
        for path, tree in modules.items()
        if QUERY_MODULE in imported_targets(tree, path)
    )
    assert not importers, (
        f"{importers} import `{QUERY_MODULE}`, which holds the statements the grant functions run "
        "against views `pulse_app` may read in full. `backend/app/services/authz.py` is the one "
        "module that may: it is where the `WHERE` clauses implementing SPEC §2.1's purview live, "
        "and one importer is what makes 'read the scoping rules in one file' true.\n"
        "An importer here has the statements and supplies its own session and its own parameters, "
        "so whatever scoping it applies is its own. The sanctioned route is to call the grant "
        "function in `authz.py`; if the function it needs does not exist yet, it belongs there."
    )
