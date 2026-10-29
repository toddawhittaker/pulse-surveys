"""Nothing under `backend/app/` names a retired cohort view, searched with a canary — E9-12 done-when 10.

> 10. … nothing under `backend/app/` names them (search with a canary) …

E9-05's sweep (`test_only_the_benchmark_service_names_the_benchmark_relations.py`)
already holds every `*.py` module's string literals. This one is the done-when's
literal search: **every file** under `backend/app/`, of any kind, read as text —
comments, docstrings, SQL and configuration included — for any of the four names
as a whole identifier.

**One exemption, and it is the migration's own input.** The downgrade recreates
the four "from their versioned files" (the ticket's Owns), so the versioned SQL
history under `views_sql/` — every `name_vNNN.sql` — must keep naming them; a file
of that shape is history the migrations replay, never a reader. Anything else
naming a view — a Python module, an unversioned SQL file, a JSON or YAML file —
is a reader or a record that goes on asserting the view exists (`docs/MISTAKES.md`
entry 1). `__pycache__` is not read: a stale bytecode file is not source.

**The canary** (`docs/MISTAKES.md` entry 3): the same matcher, run over the
exempt versioned file that defines `benchmark_cohort_week`, finds it — so a blind
matcher cannot report a clean tree. **The planted controls:** a Python comment, a
JSON file and an unversioned SQL file are flagged; a versioned file, a longer
identifier and the set functions' names are spared.

**Disclosed limits** (entry 14): a name assembled at run time is not found;
nothing outside `backend/app/` is read — `backend/migrations/` must name the views
to drop and recreate them, and `scripts/` and `frontend/` are outside the
application package this rule is about (entry 53: the enclosure is named here
rather than left implicit).

**Expected green on today's branch**: E9-05 removed the last Python reader, and
every other file naming the views is versioned history.
"""

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.invariant

REPO_ROOT = Path(__file__).resolve().parents[2]
APP_ROOT = REPO_ROOT / "backend" / "app"

RETIRED_VIEWS = (
    "benchmark_cohort_week",
    "benchmark_cohort_rating_week",
    "benchmark_cohort_term_axis",
    "benchmark_cohort_rating_term_axis",
)
NAMED = {
    view: re.compile(rf"(?<![A-Za-z0-9_]){re.escape(view)}(?![A-Za-z0-9_])")
    for view in RETIRED_VIEWS
}
VERSIONED_SQL = re.compile(r"^[a-z0-9_]+_v\d{3}\.sql$")
THE_CANARY_FILE = Path("views_sql/benchmark_cohort_week_v001.sql")


def is_history(relative: Path) -> bool:
    return (
        VERSIONED_SQL.fullmatch(relative.name) is not None and relative.parent.name == "views_sql"
    )


def names_in(text: str) -> list[str]:
    return sorted(view for view, pattern in NAMED.items() if pattern.search(text))


def offenders_under(root: Path) -> dict[str, list[str]]:
    """Every non-history file under `root` naming a retired view, by path within root."""
    found: dict[str, list[str]] = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if not path.is_file() or "__pycache__" in relative.parts or is_history(relative):
            continue
        named = names_in(path.read_text(encoding="utf-8", errors="replace"))
        if named:
            found[str(relative)] = named
    return found


PLANTED = {
    "services/benchmarks.py": "# benchmark_cohort_term_axis was the last reader.\nSET = 'benchmark_set_week'\n",
    "views_sql/benchmark_cohort_week_v001.sql": "CREATE VIEW public.benchmark_cohort_week AS SELECT 1;\n",
    "views_sql/benchmark_read_grants_v001.sql": (
        "GRANT SELECT ON public.benchmark_cohort_rating_week TO pulse_app;\n"
    ),
    "views_sql/scratch.sql": "SELECT * FROM public.benchmark_cohort_rating_term_axis;\n",
    "copy/catalog.json": '{"views": ["benchmark_cohort_week"]}\n',
    "services/rollups.py": "FLAG = 'benchmark_cohort_weekly_digest'\nSET = 'benchmark_set_rating_week'\n",
}


def test_the_matcher_sees_a_view_in_the_versioned_file_that_defines_it() -> None:
    """The canary: the exempt definition file names `benchmark_cohort_week`, and the matcher finds it.

    **A red here means the matcher is blind** (or the history file was deleted,
    which the downgrade needs).
    """
    canary = APP_ROOT / THE_CANARY_FILE
    assert canary.is_file(), (
        f"{canary.relative_to(REPO_ROOT)} does not exist; the retirement's downgrade recreates the "
        "view from it."
    )
    assert "benchmark_cohort_week" in names_in(
        canary.read_text(encoding="utf-8")
    ), f"The matcher finds nothing in {THE_CANARY_FILE}, which defines the view."


def test_the_sweep_flags_any_file_but_history_and_spares_its_near_misses(tmp_path: Path) -> None:
    """The control over a planted tree. **A red means this module is broken.**

    **The mutations it kills (in the sweep):** `*.py` only (the JSON and the
    unversioned SQL walk free); string literals only (the Python comment walks
    free); the exemption written as all of `views_sql/` (the scratch file walks
    free); a plain substring search (the longer identifier is flagged). **The
    near misses it spares:** the versioned definition and grants files, and the
    set functions' names.
    """
    for name, source in PLANTED.items():
        planted = tmp_path / name
        planted.parent.mkdir(parents=True, exist_ok=True)
        planted.write_text(source, encoding="utf-8")
    assert offenders_under(tmp_path) == {
        "copy/catalog.json": ["benchmark_cohort_week"],
        "services/benchmarks.py": ["benchmark_cohort_term_axis"],
        "views_sql/scratch.sql": ["benchmark_cohort_rating_term_axis"],
    }


def test_nothing_under_the_application_names_a_retired_cohort_view() -> None:
    """The rule over the real tree: no file but versioned SQL history names any of the four.

    **The mutation it kills:** a reader left behind (a Python module, a constant,
    an unversioned SQL file) that breaks when the views are dropped, or a
    comment still saying the view is read. **The near miss it spares:** the
    versioned files the downgrade replays.
    """
    assert APP_ROOT.is_dir(), f"{APP_ROOT} is not a directory, so this sweep walked nothing."
    assert len([path for path in APP_ROOT.rglob("*") if path.is_file()]) > 2
    found = offenders_under(APP_ROOT)
    assert not found, (
        f"These files under backend/app name a retired cohort view: {found}. README decision 10 "
        "retires all four; only the versioned SQL history may keep their names."
    )
