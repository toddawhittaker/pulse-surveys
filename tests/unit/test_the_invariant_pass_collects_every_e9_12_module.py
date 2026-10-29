"""CI's isolated §4.1 pass collects every module E9-12 adds — E9-12 done-when 11.

> 11. **CI's isolated §4.1 pass collects every new module** (no skip, no empty
>     collection).

The pass is `pytest -m invariant` from the repository root
(`.github/workflows/ci.yml`, the `invariants` leg), read afterwards by
`scripts/ci/check_invariants.py` (a skip, an xfail or an empty collection fails)
and `scripts/ci/check_invariant_assertions.py` (every marked test asserts in its
own body). Both run on the whole suite and neither can say that **this ticket's**
modules were among what ran: a module whose marker was dropped is simply not
collected, and the gate is green over everything else.

So this asks pytest itself, the way the pass does, to collect each listed module
under `-m invariant`, and requires **at least one test per module** — never a
decorator count (`docs/MISTAKES.md`: a marker held in two currencies is counted
with the collector). And it reads each module's source for the ways a collected
test can still not run: a skip or xfail mark, a `pytest.skip`, an
`importorskip`.

**The control:** a module this ticket does not add and that is `invariant`-marked
(`test_every_section_benchmarks_caller_names_the_reader.py`) is collected by the
same call; a module that is not marked (`test_env_example_sync.py`) contributes
nothing. **Not itself `invariant`-marked**: it runs pytest in a subprocess, and
the pass it inspects is the one it would otherwise sit inside.
"""

import re
import subprocess
import sys
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[2]

# Every module E9-12 adds or extends with `invariant`-marked tests.
E9_12_MODULES = (
    "tests/integration/test_e9_routes_show_a_lead_nothing_of_a_sibling_leads_course.py",
    "tests/integration/test_e9_a_lead_sees_nothing_of_a_sibling_course_on_the_seeded_institution.py",
    "tests/integration/test_e9_routes_answer_from_the_sessions_own_scope.py",
    "tests/integration/test_e9_no_comment_reaches_a_rollup_and_the_drill_down_keeps_its_hold.py",
    "tests/integration/test_e9_rollup_lists_keep_their_order_when_only_figures_change.py",
    "tests/integration/test_e9_a_leader_is_sealed_against_what_they_can_subtract.py",
    "tests/integration/test_e9_the_staff_name_definer_receives_purview_sections_only.py",
    "tests/integration/test_the_four_cohort_views_are_retired.py",
    "tests/unit/test_nothing_under_the_application_names_a_retired_cohort_view.py",
    "tests/unit/test_every_leadership_caller_of_the_staff_name_door_passes_a_scope.py",
    "tests/unit/test_only_the_leadership_scope_dependency_calls_resolve_scope.py",
    "tests/unit/test_every_section_benchmarks_caller_names_the_reader.py",
)
A_MARKED_CONTROL = "tests/unit/test_every_section_benchmarks_caller_names_the_reader.py"
AN_UNMARKED_CONTROL = "tests/unit/test_env_example_sync.py"

NOT_RUN = re.compile(r"pytest\.mark\.(skip|skipif|xfail)\b|pytest\.(skip|xfail)\(|importorskip\(")


def collected(paths: tuple[str, ...]) -> dict[str, int]:
    """How many tests `pytest --collect-only -m invariant` collects from each path."""
    completed = subprocess.run(  # noqa: S603 - this interpreter, fixed arguments, repository paths
        [
            sys.executable,
            "-m",
            "pytest",
            "--collect-only",
            "-q",
            "-m",
            "invariant",
            "-p",
            "no:cacheprovider",
            *paths,
        ],
        cwd=REPOSITORY,
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    counts = {path: 0 for path in paths}
    for line in completed.stdout.splitlines():
        node = line.strip().split("::", 1)[0]
        if node in counts and "::" in line:
            counts[node] += 1
    if completed.returncode not in (0, 5):
        raise AssertionError(
            f"Collection exited {completed.returncode}.\nstdout:\n{completed.stdout[-3000:]}\n"
            f"stderr:\n{completed.stderr[-3000:]}"
        )
    return counts


def test_the_invariant_collection_sees_a_marked_module_and_not_an_unmarked_one() -> None:
    """The control: the collection this test reads tells a marked module from an unmarked one."""
    counts = collected((A_MARKED_CONTROL, AN_UNMARKED_CONTROL))
    assert counts[A_MARKED_CONTROL] > 0 and counts[AN_UNMARKED_CONTROL] == 0, (
        f"`-m invariant` collected {counts}; the first module is marked and the second is not, "
        "so this reading cannot tell a collected module from an absent one."
    )


def test_every_e9_12_module_is_collected_by_the_invariant_pass() -> None:
    """Each module contributes at least one test to `pytest -m invariant`.

    **The mutation it kills:** an `invariant` marker dropped from one of these
    modules (it then contributes nothing and the gate stays green over the
    rest); a module deleted or renamed. **The near miss it spares:** a module
    whose controls are left unmarked beside marked criterion tests.
    """
    missing = [path for path in E9_12_MODULES if not (REPOSITORY / path).is_file()]
    assert not missing, f"These E9-12 modules do not exist: {missing}."
    counts = collected(E9_12_MODULES)
    empty = sorted(path for path, count in counts.items() if count == 0)
    assert not empty, (
        f"`pytest -m invariant` collects nothing from {empty}. CI's isolated §4.1 pass would "
        "never run them, and its gate cannot tell."
    )


def test_no_e9_12_module_carries_a_way_for_a_collected_test_not_to_run() -> None:
    """No skip or xfail mark, no `pytest.skip(`, no `importorskip(` in any of the modules.

    **The mutation it kills:** a criterion test skipped or xfailed to get past
    a red (CLAUDE.md: never). **The near miss it spares:** the words in prose,
    which this pattern does not match without the call or the mark.
    """
    found = {
        path: NOT_RUN.findall((REPOSITORY / path).read_text(encoding="utf-8"))
        for path in E9_12_MODULES
    }
    found = {path: hits for path, hits in found.items() if hits}
    assert not found, f"These modules can stop a collected invariant test from running: {found}."
