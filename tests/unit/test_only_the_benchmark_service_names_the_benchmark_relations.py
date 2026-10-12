"""One module names the benchmark relations, and it is `app.services.benchmarks` — E5-14.

**Why this sweep exists** (the E5 boundary review's invariant-coverage MEDIUM).
Every comparison figure is sealed by `comparison_after_suppression`, and E5-04's
service is where the minimums, the hero's exclusion from its own set, the lead
filter and — since E5-14 — the freeze-at-close cutoffs are applied before a set
function is ever called. The two set functions take *any* list of section ids: a
second module calling `benchmark_set_week` with one or two ids of its own
choosing gets an honest answer about those sections, and every guarantee the
service makes is simply not asked. Nothing stopped that. This does.

**The rule:** under `backend/app/`, only `services/benchmarks.py` may carry a
string that names one of the six benchmark relations E5-03 and E5-04 ship. The
six are read off the migrations, not recalled: the four views
`benchmark_cohort_week`, `benchmark_cohort_rating_week`, `benchmark_cohort_term_axis`
and `benchmark_cohort_rating_term_axis`, and the two `SECURITY DEFINER`
functions `benchmark_set_week` and `benchmark_set_rating_week`
(`backend/migrations/versions/20260913_a7c3e9d21f84_…` creates all six;
`…c4b8f37e5a19_…` and `…e7a2d5c94b31_…` re-issue three of them). After E5-14
deletes `views_sql/queries.py`'s two wrappers, that module must not name them
either — it gets no exemption here.

**What is matched.** A string literal anywhere in a module's syntax tree —
including an f-string's literal parts and one side of an implicit concatenation,
which Python has already joined — that contains a relation's name as a whole
identifier: not preceded or followed by a letter, a digit or an underscore. So
`benchmark_set_week_v003.sql` (a file name, one character of identifier past the
name) is not a use, and `public.benchmark_set_week(` is.

**What deliberately is not.** Docstrings: a module explaining in prose that it
does *not* call a set function is not calling one, and the org-views sweep
excuses docstrings for the same reason (`docs/MISTAKES.md` entry 43). Comments
are not strings and are never read.

**Its disclosed limits** (`docs/MISTAKES.md` entry 14). A name assembled at run
time — `"benchmark_" + "set_week"` — is not matched, and nothing short of
running the code would match it. And a module outside `backend/app/` is not
swept; the application package is where a request path lives.

**Controlled in both directions** (`docs/MISTAKES.md` entries 3 and 35): the
matcher is run against planted offenders and near misses under `tmp_path`, the
walk against a planted tree, and the real service module is required to be
*found* naming a relation — a matcher that can see nothing reports a clean sweep
over everything. A red in a control means these tests are broken, not the code.

**Marked `invariant`** at module level, for the same reason
`test_only_the_dependency_module_reads_a_session_from_a_request.py` is: an
instrument gone blind inside the isolated §4.1 pass would report silence as
compliance.

**Which failure a red is on today's tree:** the sweep test, naming
`views_sql/queries.py`, which still carries the two wrappers E5-14 deletes.

**E9-05 adds a second rule** (done-when 12): no module under `backend/app/`,
the service included, names one of the four cohort views, because E9-05
deletes their last reader and E9-12 drops them. Its controls are planted the
same way.
"""

import ast
import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.invariant

REPO_ROOT = Path(__file__).resolve().parents[2]
APP_ROOT = REPO_ROOT / "backend" / "app"

# The one module that may name them, as a path within the application package.
THE_SERVICE = Path("services/benchmarks.py")

# The six relations, transcribed from the migrations named in the docstring.
BENCHMARK_RELATIONS = (
    "benchmark_cohort_week",
    "benchmark_cohort_rating_week",
    "benchmark_cohort_term_axis",
    "benchmark_cohort_rating_term_axis",
    "benchmark_set_week",
    "benchmark_set_rating_week",
)

# A relation's name as a whole identifier. The lookarounds are what spare a file
# name like `benchmark_set_week_v003.sql` and a longer relation like
# `benchmark_cohort_rating_week` when the shorter `benchmark_cohort_week` is sought
# (they share no whole-identifier match, but a substring search would conflate them).
NAMED = {
    relation: re.compile(rf"(?<![A-Za-z0-9_]){re.escape(relation)}(?![A-Za-z0-9_])")
    for relation in BENCHMARK_RELATIONS
}


def docstring_nodes(tree: ast.AST) -> set[int]:
    """The ids of every docstring constant in `tree`: module, class and function."""
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


def relations_named_in(source: str, where: str) -> list[str]:
    """Every benchmark relation a module's non-docstring string literals name, sorted."""
    try:
        tree = ast.parse(source, filename=where)
    except SyntaxError as failure:  # pragma: no cover - a broken source tree
        pytest.fail(
            f"{where} does not parse ({failure}), so this sweep cannot read it and would report it "
            "clean having read nothing."
        )
    excused = docstring_nodes(tree)
    found: set[str] = set()
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and id(node) not in excused
        ):
            found.update(
                relation for relation, pattern in NAMED.items() if pattern.search(node.value)
            )
    return sorted(found)


def offenders_under(root: Path, exempt: Path) -> dict[str, list[str]]:
    """Every module under `root`, other than `exempt`, naming a relation — by path within root."""
    return {
        str(path.relative_to(root)): named
        for path in sorted(root.rglob("*.py"))
        if path.relative_to(root) != exempt
        and (named := relations_named_in(path.read_text(encoding="utf-8"), str(path)))
    }


PLANTED_OFFENDERS = {
    # The plain call, as a second service would write it.
    "planted_plain_call.py": (
        "from sqlalchemy import text\n\n\n"
        "def figures(session, ids):\n"
        "    return session.execute(text('SELECT * FROM public.benchmark_set_week(:ids)'), "
        "{'ids': ids})\n"
    ),
    # An f-string: the relation is in a literal part, the rest is interpolated.
    "planted_f_string.py": (
        "def statement(columns):\n"
        "    return f'SELECT {columns} FROM public.benchmark_cohort_rating_term_axis'\n"
    ),
    # Implicit concatenation, which the parser joins into one constant.
    "planted_concatenation.py": (
        "STATEMENT = (\n"
        "    'SELECT workload_mean '\n"
        "    'FROM benchmark_cohort_week WHERE course_week = 2'\n"
        ")\n"
    ),
    # A name held in a constant and used somewhere else.
    "planted_constant.py": "RATING_FUNCTION = 'benchmark_set_rating_week'\n",
}

PLANTED_NEAR_MISSES = {
    # A versioned SQL file name: one identifier character past the relation.
    "planted_file_name.py": "SQL_FILE = 'benchmark_set_week_v003.sql'\n",
    # The name in a docstring and a comment, calling nothing.
    "planted_prose.py": (
        '"""This module never calls benchmark_set_week; the service does."""\n\n'
        "# benchmark_cohort_week is E5-03's view.\n\n\n"
        "def ping():\n"
        '    """Nothing here reads benchmark_cohort_term_axis."""\n'
        "    return 'pong'\n"
    ),
    # A longer identifier that merely begins with a relation's name.
    "planted_longer_name.py": "FLAG = 'benchmark_set_weekly_digest_enabled'\n",
    # The owner role and the grants file, which share the prefix and are not relations.
    "planted_owner.py": "OWNER = 'pulse_benchmark_definer'\nGRANTS = 'benchmark_read_grants'\n",
}

PLANTED_TREE = {
    # Exempt: the service. It really does name a relation.
    "services/benchmarks.py": "SET = 'benchmark_set_week'\n",
    # The offender one directory away: a report module calling a set function itself.
    "services/reporting.py": "SQL = 'SELECT * FROM benchmark_set_week(:ids)'\n",
    # The offender the deletion is about: a query module keeping a wrapper.
    "views_sql/queries.py": "WRAPPER = 'benchmark_set_rating_week'\n",
    # Not offenders.
    "api/leadership.py": '"""Named sets resolve through benchmark_set_week, in the service."""\n',
    "views_sql/__init__.py": "FILES = ('benchmark_cohort_week_v001.sql',)\n",
}


def test_the_matcher_finds_the_relation_the_service_really_names() -> None:
    """The control on the sweep (`docs/MISTAKES.md` entry 35): it can see a real one.

    `services/benchmarks.py` calls the two set functions, so it certainly carries
    at least one of their names in a string. A matcher that cannot find one there
    would report every other module clean having read nothing.

    **A red here means this module is broken** — or the service no longer names a
    set function, in which case the rule below is about nothing and needs
    restating rather than its matcher fixing.
    """
    service = APP_ROOT / THE_SERVICE
    assert service.is_file(), (
        f"{service.relative_to(REPO_ROOT)} does not exist. SPEC §13 names it, and it is the one "
        "module this sweep exempts."
    )
    named = relations_named_in(service.read_text(encoding="utf-8"), str(service))
    assert set(named) & {"benchmark_set_week", "benchmark_set_rating_week"}, (
        f"The matcher found {named} in {service.relative_to(REPO_ROOT)}, which calls the benchmark "
        "set functions. It can therefore see nothing, and the sweep below would pass over any "
        "module in the package."
    )


def test_the_matcher_flags_planted_uses_and_spares_its_near_misses(tmp_path: Path) -> None:
    """The instrument, both directions, on planted modules. **A red means this module is broken.**

    **The mutations this kills:** the matcher widened to a plain substring search,
    which flags the file name, the longer identifier and the definer role; the
    matcher narrowed to whole-string equality, which spares the plain call, the
    f-string and the concatenation; and the docstring exemption dropped, which
    flags the prose module.
    """
    for name, source in {**PLANTED_OFFENDERS, **PLANTED_NEAR_MISSES}.items():
        (tmp_path / name).write_text(source, encoding="utf-8")
    planted = sorted(tmp_path.glob("*.py"))
    assert len(planted) == len(PLANTED_OFFENDERS) + len(PLANTED_NEAR_MISSES)

    flagged = {
        path.name
        for path in planted
        if relations_named_in(path.read_text(encoding="utf-8"), str(path))
    }
    assert flagged == set(PLANTED_OFFENDERS), (
        f"The matcher flagged {sorted(flagged)}; the planted uses are {sorted(PLANTED_OFFENDERS)} "
        f"and the planted near misses {sorted(PLANTED_NEAR_MISSES)}."
    )


def test_the_walk_reaches_every_directory_and_spares_only_the_service(tmp_path: Path) -> None:
    """The control on the walk. **A red means this module is broken.**

    **The mutations this kills:** the walk narrowed to one directory, under which
    one of the two offenders is not found; and the exemption written as a
    directory (`services/`), under which `services/reporting.py` walks free.
    """
    for name, source in PLANTED_TREE.items():
        planted = tmp_path / name
        planted.parent.mkdir(parents=True, exist_ok=True)
        planted.write_text(source, encoding="utf-8")

    found = offenders_under(tmp_path, THE_SERVICE)
    assert set(found) == {"services/reporting.py", "views_sql/queries.py"}, (
        f"The walk returned {sorted(found)} over the planted tree; its offenders are "
        "`services/reporting.py` and `views_sql/queries.py`, and `services/benchmarks.py` is "
        "the one exemption."
    )


# E9-05 done-when 12: after `named_set_term_axis` is deleted, the four cohort views
# have no reader under `backend/app/`, **the benchmark service included**, so that
# E9-12 can retire them. The interface for E9-05 narrows the check to Python
# modules (ruling 3 there): `views_sql/*.sql` defines the views until E9-12 drops
# them, and a `.sql` file is not a reader.
COHORT_VIEWS = (
    "benchmark_cohort_week",
    "benchmark_cohort_rating_week",
    "benchmark_cohort_term_axis",
    "benchmark_cohort_rating_term_axis",
)

# The four names a deleted read leaves behind, by E9-05's interface: "Deleted:
# `named_set_trend`, `named_set_workload`, `named_set_term_axis`, `TermAxisPoint`".
# (`_COHORT_TERM_AXIS`, the fifth, is a private constant; the cohort sweep below
# finds the string it held.)
DELETED_NAMED_SET_READS = (
    "named_set_trend",
    "named_set_workload",
    "named_set_term_axis",
    "TermAxisPoint",
)


def cohort_views_named_under(root: Path) -> dict[str, list[str]]:
    """Every module under `root`, with no exemption, naming one of the four cohort views."""
    return {
        str(path.relative_to(root)): named
        for path in sorted(root.rglob("*.py"))
        if (
            named := [
                relation
                for relation in relations_named_in(path.read_text(encoding="utf-8"), str(path))
                if relation in COHORT_VIEWS
            ]
        )
    }


def test_the_cohort_view_sweep_spares_no_module_and_sees_a_planted_reader(tmp_path: Path) -> None:
    """The control on the cohort-view sweep, both directions. **A red means this test is broken.**

    `docs/MISTAKES.md` entry 3's canary: a planted `services/benchmarks.py` that
    holds a cohort-view read (the shape `_COHORT_TERM_AXIS` had) must be found —
    the exemption the rule above grants the service is exactly what this sweep
    must not grant — and a planted module naming only a set function, or a
    versioned SQL file name, must be spared.

    **The mutations this kills:** the cohort sweep reusing `offenders_under` with
    the service exempt (the planted service read walks free); a sweep narrowed to
    the set functions; the four views transcribed short by one.
    """
    planted = {
        "services/benchmarks.py": (
            "_COHORT_TERM_AXIS = 'SELECT * FROM public.benchmark_cohort_term_axis'\n"
            "SET = 'benchmark_set_week'\n"
        ),
        "services/rollups.py": "SQL = 'SELECT 1 FROM benchmark_cohort_rating_week'\n",
        "services/other.py": "SET = 'benchmark_set_rating_week'\n",
        "views_sql/__init__.py": "FILES = ('benchmark_cohort_week_v001.sql',)\n",
    }
    for name, source in planted.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source, encoding="utf-8")

    found = cohort_views_named_under(tmp_path)
    assert found == {
        "services/benchmarks.py": ["benchmark_cohort_term_axis"],
        "services/rollups.py": ["benchmark_cohort_rating_week"],
    }, f"The cohort-view sweep returned {found} over the planted tree."


@pytest.mark.invariant
def test_no_module_under_the_application_names_a_cohort_view_the_benchmark_service_included() -> (
    None
):
    """E9-05 done-when 12: nothing under `backend/app/**/*.py` names a cohort view.

    `named_set_term_axis` was the last reader of `benchmark_cohort_term_axis`
    (README fact list), and E9-05 deletes it with `TermAxisPoint` and
    `_COHORT_TERM_AXIS`. After that no Python module may name any of the four
    views, and `services/benchmarks.py` gets **no** exemption here, unlike the
    rule above.

    **The canary in the body** (`docs/MISTAKES.md` entry 3): the same matcher,
    run over the real service, finds a set function's name there — so a blind
    matcher cannot report this sweep clean.

    **The mutation it kills:** `named_set_term_axis` (or its SQL constant) left in
    `benchmarks.py`; any new module reading a cohort view, which E9-12 would then
    break by dropping it. **Expected red before E9-05 lands:** this assertion,
    naming `services/benchmarks.py` and `benchmark_cohort_term_axis`.
    """
    service = APP_ROOT / THE_SERVICE
    canary = relations_named_in(service.read_text(encoding="utf-8"), str(service))
    assert set(canary) & {"benchmark_set_week", "benchmark_set_rating_week"}, (
        f"The matcher found {canary} in {THE_SERVICE}, which calls the set functions, so it can "
        "see nothing and the sweep below would pass over every module."
    )

    found = cohort_views_named_under(APP_ROOT)
    assert not found, (
        f"These modules under backend/app name a cohort view: {found}. E9-05 deletes the last "
        "reader (`named_set_term_axis`), README decision 10 leaves the four views unread, and "
        "E9-12 drops them. A reader left behind breaks when they go."
    )


@pytest.mark.invariant
def test_the_deleted_named_set_reads_are_gone_from_the_benchmark_service() -> None:
    """E9-05 done-when 12's first clause, and the interface's deletions.

    `named_set_term_axis` answers a set's declared length and level
    institution-wide and cannot be scoped to a reader, and `named_set_trend` and
    `named_set_workload` take no reader at all. E9-05 replaces all three with
    `named_set_series`, which takes the reader's scope. A reader-less door left
    in place is a door some later caller uses.

    **The control in the body:** the module imports and exposes the replacement,
    `named_set_series`, so "absent" is not a module that failed to load.

    **The mutation it kills:** any of the four kept beside the new door.
    **Expected red before E9-05 lands:** the first assertion, naming
    `named_set_series` as missing.
    """
    import importlib

    module = importlib.import_module("app.services.benchmarks")
    assert callable(getattr(module, "named_set_series", None)), (
        "`app.services.benchmarks` exposes no `named_set_series`, E9-05's one named-set door "
        "taking the reader's scope and the viewed term."
    )
    left = [name for name in DELETED_NAMED_SET_READS if hasattr(module, name)]
    assert not left, (
        f"`app.services.benchmarks` still defines {left}. E9-05 deletes them: none takes a reader, "
        "and `named_set_term_axis` cannot be narrowed to one."
    )


def test_no_module_but_the_benchmark_service_names_a_benchmark_relation() -> None:
    """The rule: only `app/services/benchmarks.py` names the six benchmark relations.

    **The mutation this kills:** any other module under `backend/app/` calling a
    set function or reading a cohort view itself — a report helper, a job, a
    leadership route, or `views_sql/queries.py` keeping the wrappers E5-14
    deletes. Each would compute a figure over sections the service never chose,
    with no hero exclusion, no lead filter and no cutoff, and hand it to the
    chokepoint as though it were a benchmark.

    **The non-emptiness control:** the package has to hold more than the one
    exempt module, or "no other module names one" is a statement about nothing.
    """
    assert APP_ROOT.is_dir(), f"{APP_ROOT} is not a directory, so this sweep walked nothing."
    swept = [path for path in APP_ROOT.rglob("*.py") if path.relative_to(APP_ROOT) != THE_SERVICE]
    assert len(swept) > 1, f"{APP_ROOT} holds next to nothing beyond {THE_SERVICE}."

    offenders = offenders_under(APP_ROOT, THE_SERVICE)
    assert not offenders, "\n".join(
        [
            "These modules under backend/app name a benchmark relation, which only "
            f"`{THE_SERVICE}` may do:",
            *(f"  {path}: {', '.join(named)}" for path, named in sorted(offenders.items())),
            "",
            "The set functions answer for any section ids they are handed. The service is where "
            "the default set, the university line and a named set are resolved, the hero is "
            "excluded from its own set, and each week's cutoff is applied — a second caller gets "
            "none of it. Route the read through `app.services.benchmarks`.",
        ]
    )
