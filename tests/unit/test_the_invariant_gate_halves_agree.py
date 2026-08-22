"""The two halves of the §4.1 invariant gate count the same tests — E0-40 decision 4.

The gate that protects SPEC §4.1 is two programs reading two different things.
`scripts/ci/check_invariants.py` reads the JUnit XML a run produced, so it sees
what *ran*: a skip, an xfail, an empty collection.
`scripts/ci/check_invariant_assertions.py` reads the sources, so it sees what is
*written*: a marked test whose body asserts nothing. Both callers run both, in
that order — `.github/workflows/ci.yml`'s invariant step and the `Makefile`'s
`invariants` target — and `tests/unit/test_invariant_gate_is_strict.py` is what
holds them to it.

**Neither half can see the gap between them, and until now nothing compared their
numbers.** The run half collects whatever `testpaths` in `pyproject.toml` points
at; the source half is handed the whole `tests` tree. While those two agree the
gate is whole. The moment they do not — a `tests/property/` directory holding a
property-based §4.1 invariant, which is a thing this project intends to write —
the scan counts the file, reports every marked test asserts something, and exits
0, while the run collects it not at all. Two green checkmarks over an invariant
that never executed. E0-40 sets `testpaths = ["tests"]` so that a new directory
is included rather than dropped, and this is the test that notices if that ever
stops being true.

**What is compared is functions, not test items.** A parametrised invariant is
one function and several collected ids; the source half counts the `def`. So the
collected ids are stripped of their parametrisation and de-duplicated before the
two numbers are put beside each other, and a number that moved because somebody
added a case to a table is not reported as a hole in the gate.

**Both halves are executed here rather than modelled.** A reimplementation of
either count inside this module would be a second definition of the thing being
compared, free to drift from both (`docs/MISTAKES.md` entry 19); the point of the
test is that the two programs the pipeline runs agree, so the two programs the
pipeline runs are what it runs.

**The third test is the anchor under the other two.** E0-40 decision 8 asks for
`testpaths` to be asserted as exactly `["tests"]`, and that is not a restatement
of the comparison: the comparison notices a narrow `testpaths` only once somebody
has written an invariant in a directory it excludes, whereas the setting is the
thing a later pull request reverts while tidying — a revert that changes not one
collected test on the day it lands. The cause and the consequence each have a
test, and neither covers the other.

**This module is not itself marked `invariant`**, deliberately. It asserts
nothing about what a student can see — it is a guard on the machinery that
protects those assertions — and marking it would make it a term in the sum it is
comparing.
"""

import re
import subprocess
import sys
import tomllib
from collections import Counter
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# Read with `tomllib`, which is how three modules in this suite already read this
# file, rather than searched as text. A text search has to guess at quoting and
# wrapping and would pass over a second `testpaths` further down the block; the
# parser answers with the value pytest itself will use.
PYPROJECT = REPO_ROOT / "pyproject.toml"

# E0-40 decision 4. Identical collection today — only `tests/unit` and
# `tests/integration` hold Python tests, and `tests/e2e` holds TypeScript that
# pytest does not collect — and a directory added later is included rather than
# silently dropped.
COLLECTED_TREE = ["tests"]

# The source half of the gate, invoked the way both callers invoke it. Named here
# rather than discovered: `tests/unit/test_invariant_gate_is_strict.py` is what
# pins the callers to this path, so if it moves, that module fails first and says
# so.
ASSERTION_CHECKER = REPO_ROOT / "scripts" / "ci" / "check_invariant_assertions.py"

MARKER = "invariant"

# What the callers hand the source half. The run half is given no path at all —
# `pytest -m invariant` — which is the whole point: it collects whatever
# `testpaths` says, and this test exists because those two inputs are different
# ways of naming what ought to be one set of files.
SCANNED_TREE = "tests"

# Collecting the suite imports every test module. That is seconds, not minutes;
# a run longer than this is a collection doing something other than collecting.
TIMEOUT_SECONDS = 300

# A node id as `--collect-only -q` prints it, one per line. Anchored on `.py::` so
# that the summary line, a warning line (`path.py:31: SomeWarning`) and an
# `ERROR collecting …` line are not read as collected tests.
NODE_ID = re.compile(r"^\S+\.py::\S.*$")

# The parametrisation of an id, which is the difference in currency between the
# two halves.
PARAMETRISATION = re.compile(r"\[[^\[\]]*\]$")

# The source half's verdict line, printed on success. Parsed rather than
# recomputed, so this module reads the number the pipeline reads.
SCANNED_TOTAL = re.compile(r"^OK:\s*(?P<total>\d+)\s+invariant-marked test", re.MULTILINE)

# ---------------------------------------------------------------------------
# The planted tree for the control below: two marked invariants, in two
# directories, one of which `testpaths` names and one of which it does not. This
# is the divergence written down as a repository, so that the comparison above is
# shown catching it rather than asserted to be capable of catching it
# (`docs/MISTAKES.md` entry 9 — a guard that has never been run is a comment).
# ---------------------------------------------------------------------------
COLLECTED_DIRECTORY = "probe/collected"
UNCOLLECTED_DIRECTORY = "probe/uncollected"
PROBE_TREE = "probe"

COLLECTED_TEST = "test_inside_the_collected_directory"
UNCOLLECTED_TEST = "test_outside_the_collected_directory"

PLANTED_INI = f"""[pytest]
markers =
    {MARKER}: a SPEC §4.1 confidentiality invariant; may never be skipped
testpaths = {COLLECTED_DIRECTORY}
"""


def planted_invariant(name: str) -> str:
    """A module holding one marked invariant that asserts something.

    It asserts, so the source half accepts it; it is marked, so both halves are
    looking for it. The only thing that differs between the two copies is which
    directory it is written into.
    """
    return f"import pytest\n\n\n@pytest.mark.{MARKER}\ndef {name}() -> None:\n    assert True\n"


def collected_invariant_functions(cwd: Path) -> set[str]:
    """The distinct marked test functions `pytest -m invariant` collects from `cwd`.

    No path argument, because that is how both callers run it and because the
    argument is exactly what is under test: with none, `testpaths` decides, and a
    directory outside `testpaths` is silently not collected.
    """
    command = [
        sys.executable,
        "-m",
        "pytest",
        "-m",
        MARKER,
        "--collect-only",
        "-q",
        "-p",
        "no:cacheprovider",
    ]
    try:
        # S603: the executable is this interpreter, and every argument is a
        # literal written in this file.
        completed = subprocess.run(  # noqa: S603
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
            timeout=TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        pytest.fail(
            f"Collecting the invariant suite in {cwd} took more than {TIMEOUT_SECONDS}s. That is "
            "a collection doing something other than collecting; the pipeline runs this same "
            "command on every pull request."
        )

    if completed.returncode != 0:
        pytest.fail(
            f"`pytest -m {MARKER} --collect-only` exited {completed.returncode} in {cwd}, so "
            "there is no collected set to compare.\n"
            f"  stdout: {completed.stdout.strip()[-1200:] or '(nothing)'}\n"
            f"  stderr: {completed.stderr.strip()[-800:] or '(nothing)'}\n"
            "\n"
            "Reported rather than read as an empty collection. An empty set would make the "
            "comparison in this module fail for a reason that has nothing to do with the two "
            "halves of the gate disagreeing, and a collection error means the invariant pass "
            "itself cannot run."
        )

    found: set[str] = set()
    for raw in completed.stdout.splitlines():
        line = raw.strip()
        if NODE_ID.match(line):
            found.add(PARAMETRISATION.sub("", line))
    return found


def scanned_invariant_functions(cwd: Path, target: str) -> int:
    """The number the source half reports over `target`, run from `cwd`."""
    if not ASSERTION_CHECKER.is_file():
        pytest.fail(
            f"{ASSERTION_CHECKER} does not exist, so half of the §4.1 gate is missing and there "
            "is no second number to compare. `tests/unit/test_invariant_gate_is_strict.py` is "
            "what asserts both callers invoke it; if it has moved, this constant moves with it."
        )

    try:
        # S603: the executable is this interpreter, the script is this
        # repository's own, and the target is a literal written in this file.
        completed = subprocess.run(  # noqa: S603
            [sys.executable, str(ASSERTION_CHECKER), target],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
            timeout=TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        pytest.fail(
            f"{ASSERTION_CHECKER.name} took more than {TIMEOUT_SECONDS}s over {target} in {cwd}."
        )

    if completed.returncode != 0:
        pytest.fail(
            f"{ASSERTION_CHECKER.name} exited {completed.returncode} over `{target}` in {cwd}, so "
            "it reported no total to compare.\n"
            f"  stdout: {completed.stdout.strip()[-800:] or '(nothing)'}\n"
            f"  stderr: {completed.stderr.strip()[-1200:] or '(nothing)'}\n"
            "\n"
            "That checker exits non-zero for a marked test that asserts nothing and for a scan "
            "that found none at all. Either is a failure of the gate rather than of this "
            "comparison, and it is reported here rather than turned into a number."
        )

    match = SCANNED_TOTAL.search(completed.stdout)
    if match is None:
        pytest.fail(
            f"{ASSERTION_CHECKER.name} succeeded over `{target}` and printed no line this module "
            "can read a total out of.\n"
            f"  stdout: {completed.stdout.strip()[:800] or '(nothing)'}\n"
            "\n"
            "The total is parsed from the checker's own output rather than recomputed here, so "
            "that this test compares the number the pipeline sees. A changed verdict line needs "
            "this pattern changed with it — and failing loudly is the point: a reader that "
            "silently found nothing would report zero, and zero equals zero."
        )
    return int(match.group("total"))


def test_the_collector_and_the_assertion_scan_count_the_same_invariant_tests() -> None:
    """E0-40 decision 4: neither half of the §4.1 gate can hold a number the other does not.

    `pytest -m invariant` collects what `testpaths` names.
    `check_invariant_assertions.py tests` reads the whole test tree. Nothing has
    ever compared the two totals, so a §4.1 invariant written in a directory
    outside `testpaths` is counted by the scan, reported as asserting something,
    and never run — with the invariant pass green and the required check green.
    That is not a hypothetical shape: the property-based invariants this project
    plans belong in a directory that does not exist yet, and the first one to
    arrive would land in exactly that gap.

    **Functions on both sides.** The scan counts `def`s; the collector counts
    items, and a parametrised invariant is several items for one `def`. The ids
    are stripped of their parametrisation before they are counted, so adding a
    case to a table does not read as a hole in the gate.

    **The two non-zero assertions are the ones that make the equality mean
    something**, and they are not ceremony: zero equals zero, so a collector that
    found nothing and a scan that found nothing would agree perfectly while every
    §4.1 assertion in the repository had been deleted. The scan already refuses
    its own zero — that is E0-36 item 3 — and the collector's is asserted here
    because nothing else in this module would notice it.

    **The mutation this test kills:** put a marked, asserting §4.1 invariant in a
    test directory `testpaths` does not name — `tests/property/`, say — and leave
    `pyproject.toml` alone. The scan's number goes up, the collector's does not,
    and this is the only thing in the repository that says so.

    **The near misses that must stay green:** a new invariant under `tests/unit`
    or `tests/integration`, which moves both numbers together; a new
    parametrisation on an existing invariant, which moves neither; and moving an
    invariant from one collected directory to another.
    """
    collected = collected_invariant_functions(REPO_ROOT)
    scanned = scanned_invariant_functions(REPO_ROOT, SCANNED_TREE)

    assert collected, (
        f"`pytest -m {MARKER}` collected no test at all, so the equality below would be satisfied "
        "by two zeroes.\n"
        "\n"
        "CLAUDE.md: the §4.1 invariant suite may never be skipped, and CI treats an empty "
        "collection as a failure for this exact reason — a green checkmark over nothing looks "
        "like a green checkmark over everything."
    )
    assert scanned, (
        f"{ASSERTION_CHECKER.name} reported no marked test under `{SCANNED_TREE}`, so the "
        "equality below would be satisfied by two zeroes. That checker refuses its own zero, so "
        "reaching this assertion means its verdict line was misread rather than that it found "
        "nothing."
    )

    by_directory = Counter(str(Path(node.split("::")[0]).parent) for node in collected)

    assert len(collected) == scanned, "\n".join(
        [
            "The two halves of the §4.1 invariant gate disagree about how many invariant tests "
            "this repository has:",
            f"  collected by `pytest -m {MARKER}`:                 {len(collected)} function(s)",
            f"  read by {ASSERTION_CHECKER.name} {SCANNED_TREE}:  {scanned} function(s)",
            "",
            "  collected from:",
            *(f"    {directory}: {count}" for directory, count in sorted(by_directory.items())),
            "",
            "The collector is bounded by `testpaths` in `pyproject.toml` and the scan is handed "
            "the whole `tests` tree, so the usual cause is a test directory `testpaths` does not "
            "name. The invariant in it is counted, reported as asserting something, and never "
            "run — and both halves of the gate exit 0.",
            "",
            "The repair is `testpaths`, not this test. Narrowing the scan to match the collector "
            "would make the two numbers agree by making the source half blind to the same "
            "directory, which is the failure written down twice rather than fixed.",
            "",
            "If the difference is the other way round — more collected than scanned — then the "
            "collector is reaching tests the scan cannot read, and a marked test that asserts "
            "nothing could be sitting in one of them.",
        ]
    )


def test_the_comparison_notices_an_invariant_the_collector_never_reaches(tmp_path: Path) -> None:
    """The control: the divergence is planted, and both halves are shown answering differently.

    The test above passes today and is meant to. What it cannot show, on a tree
    where the two halves already agree, is that it *would* notice if they stopped
    — a reader that miscounted, a verdict line parsed wrongly, a collector whose
    output shape changed would all report agreement just as loudly. So the
    divergence is written down as a repository here: two marked invariants in two
    directories, a `pytest.ini` naming only one of them in `testpaths`, and both
    halves of the gate run over it exactly as they are run over the real tree.

    The scan must see two. The collector must see one, and it must be the one in
    the named directory rather than either of them. Then the number the test above
    compares is a number that can differ, and its green means something.

    **This is the shape `docs/MISTAKES.md` entry 3 asks for** — run the check
    against the case you claim it catches as well as the case you claim it allows
    — and entry 9's rule that a guard nobody has executed is a comment.

    **The mutation this test kills:** any weakening of the comparison that makes
    it structurally unable to see a difference — counting node ids from the scan's
    own output, taking the maximum of the two, comparing files rather than
    functions. **The near miss that must stay green:** a change to how ids are
    printed or to the checker's verdict wording, which fails in the readers above
    with a message naming what it could not parse rather than here.
    """
    (tmp_path / "pytest.ini").write_text(PLANTED_INI, encoding="utf-8")
    for directory, name in (
        (COLLECTED_DIRECTORY, COLLECTED_TEST),
        (UNCOLLECTED_DIRECTORY, UNCOLLECTED_TEST),
    ):
        planted = tmp_path / directory
        planted.mkdir(parents=True)
        (planted / f"{name}.py").write_text(planted_invariant(name), encoding="utf-8")

    scanned = scanned_invariant_functions(tmp_path, PROBE_TREE)
    assert scanned == 2, (
        f"The source half read {scanned} marked test(s) under a planted tree holding exactly two, "
        f"one in `{COLLECTED_DIRECTORY}` and one in `{UNCOLLECTED_DIRECTORY}`.\n"
        "\n"
        "It reads sources and knows nothing about `testpaths`, which is the whole reason the two "
        "halves can disagree. If it cannot see both of these, the test above is comparing "
        "something other than what it says it is."
    )

    collected = collected_invariant_functions(tmp_path)
    assert collected == {f"{COLLECTED_DIRECTORY}/{COLLECTED_TEST}.py::{COLLECTED_TEST}"}, (
        f"The collector found {sorted(collected)} in a planted tree whose `pytest.ini` sets "
        f"`testpaths = {COLLECTED_DIRECTORY}`.\n"
        "\n"
        f"It should find exactly the one invariant in `{COLLECTED_DIRECTORY}` and nothing in "
        f"`{UNCOLLECTED_DIRECTORY}` — that silence is the defect E0-40 decision 4 is about. "
        "Finding both would mean this control cannot reproduce the divergence; finding neither "
        "would mean the reader above cannot see a collected test at all, and the comparison it "
        "feeds would then agree at zero over the real tree as well."
    )

    assert len(collected) < scanned, (
        f"Over a tree with an invariant outside `testpaths`, the two halves reported "
        f"{len(collected)} and {scanned} and this control needs them to differ.\n"
        "\n"
        "With these two numbers equal, the comparison in this module is structurally incapable "
        "of failing, and its green over the real repository says nothing about whether the §4.1 "
        "invariant suite runs everything the scan approves."
    )


def test_the_collector_is_pointed_at_the_whole_test_tree() -> None:
    """E0-40 decision 4, at the cause rather than the consequence: `testpaths` is `["tests"]`.

    The comparison above notices the *effect* of a narrow `testpaths` — a marked
    invariant the scan counts and the run never collects — and it can only notice
    it once such a test exists. This notices the setting itself, which is the
    thing a later pull request reverts by tidying, and it notices it on the day of
    the revert rather than on the day somebody writes a test in a new directory.
    Cause and consequence, and neither substitutes for the other: widening
    `testpaths` with the scan pointed somewhere narrower would satisfy this and
    fail that.

    Collection is identical today, which is what makes this cheap to hold:
    `tests/unit` and `tests/integration` are the only directories under `tests`
    holding Python, and `tests/e2e` holds TypeScript pytest does not collect. What
    changes is the default for the next directory — included rather than dropped
    in silence.

    **The mutation this test kills:** put `testpaths` back to
    `["tests/unit", "tests/integration"]`, which changes not one collected test
    today and quietly restores the gap. **The near miss that must stay green:**
    adding a directory under `tests/`, which needs no edit here at all — that
    being true is the point of the setting.
    """
    assert PYPROJECT.is_file(), (
        f"{PYPROJECT} does not exist, so nothing in this repository says which directories pytest "
        "collects and the invariant pass runs over whatever the invocation happens to name."
    )

    document = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    options = document.get("tool", {}).get("pytest", {}).get("ini_options", {})
    assert options, (
        f"{PYPROJECT.name} has no `[tool.pytest.ini_options]` table, so `testpaths`, the marker "
        "registrations and `--strict-markers` are all absent — and `pytest -m invariant` against "
        "an unregistered marker is a very different gate from the one CLAUDE.md describes."
    )

    testpaths = options.get("testpaths")
    assert testpaths == COLLECTED_TREE, (
        f"`testpaths` is {testpaths!r} and E0-40 decision 4 settles {COLLECTED_TREE!r}.\n"
        "\n"
        "The invariant pass runs `pytest -m invariant` with no path, so `testpaths` is the whole "
        "of what it collects, while `check_invariant_assertions.py` is handed `tests`. A "
        "`testpaths` narrower than the scanned tree is a §4.1 invariant that can be written, "
        "counted, approved and never run — with both halves of the gate exiting 0 and the "
        "required check green.\n"
        "\n"
        "It is one entry rather than two because a directory nobody has added yet is exactly the "
        "one that would be left out of a list somebody maintains by hand."
    )
