"""Assert that the sharded unit and integration pass ran the whole suite, once.

CI splits `pytest tests/unit tests/integration` across several runners
(docs/adr/0181). Each runner loads `scripts/ci/pytest_shard.py`, which keeps one
slice of the collection and records two lists beside its JUnit XML:
`collected.txt`, everything pytest collected before the slice was taken, and
`selected.txt`, the slice itself.

A shard that ran green proves only that its own slice passed. Nothing in a green
shard says the slices covered the suite, so a slicing bug — an off-by-one, two
runners told the same slice, a shard that never started — would read as a
smaller suite passing. This checker is what turns that into a red job. It fails
unless every one of these holds:

  * exactly the expected number of shard directories are present, each holding
    `collected.txt`, `selected.txt` and `pytest.xml`;
  * every shard collected the same non-empty list of tests;
  * the slices are pairwise disjoint and their union is that list, with no test
    left out;
  * each shard's JUnit XML — written by pytest, not by the slicing plugin — holds
    exactly as many test cases as its slice, so a selected test that never
    reached the report is caught by a reader other than the code that chose it.

Standard library only: it runs before any dependency is installed.

Usage:
    check_test_shards.py --expected 3 SHARD_DIR [SHARD_DIR ...]

Each SHARD_DIR holds `reports/shard/collected.txt`, `reports/shard/selected.txt`
and `reports/pytest.xml`, the layout the workflow uploads.
"""

from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

COLLECTED = Path("reports/shard/collected.txt")
SELECTED = Path("reports/shard/selected.txt")
JUNIT = Path("reports/pytest.xml")


def read_list(path: Path) -> list[str]:
    return [line for line in path.read_text(encoding="utf-8").splitlines() if line]


def junit_cases(path: Path) -> int:
    # S314: the input is JUnit XML pytest wrote in this pipeline, not user input.
    root = ET.parse(path).getroot()  # noqa: S314
    return sum(1 for _ in root.iter("testcase"))


def check(expected: int, shard_dirs: list[Path]) -> list[str]:
    problems: list[str] = []

    if len(shard_dirs) != expected:
        problems.append(
            f"expected {expected} shard directories and was given {len(shard_dirs)}: "
            f"{[str(d) for d in shard_dirs]}"
        )

    collected: dict[Path, list[str]] = {}
    selected: dict[Path, list[str]] = {}
    cases: dict[Path, int] = {}
    for shard in shard_dirs:
        missing = [
            str(name) for name in (COLLECTED, SELECTED, JUNIT) if not (shard / name).is_file()
        ]
        if missing:
            problems.append(f"{shard}: missing {missing} — this shard did not record its run")
            continue
        collected[shard] = read_list(shard / COLLECTED)
        selected[shard] = read_list(shard / SELECTED)
        cases[shard] = junit_cases(shard / JUNIT)

    if problems:
        return problems

    reference_shard = shard_dirs[0]
    reference = collected[reference_shard]
    if not reference:
        problems.append(f"{reference_shard}: collected no tests at all")
    if len(set(reference)) != len(reference):
        problems.append(f"{reference_shard}: the collection names a test more than once")
    for shard in shard_dirs[1:]:
        if collected[shard] != reference:
            problems.append(
                f"{shard} collected a different list from {reference_shard} "
                f"({len(collected[shard])} tests against {len(reference)}), so the slices "
                "were taken over different suites"
            )

    seen: dict[str, Path] = {}
    for shard in shard_dirs:
        if not selected[shard]:
            problems.append(f"{shard}: its slice is empty")
        for nodeid in selected[shard]:
            if nodeid in seen:
                problems.append(f"{nodeid} ran in both {seen[nodeid]} and {shard}")
            seen[nodeid] = shard

    left_out = [nodeid for nodeid in reference if nodeid not in seen]
    if left_out:
        problems.append(f"{len(left_out)} collected test(s) ran in no shard, for example:")
        problems.extend(f"  {nodeid}" for nodeid in left_out[:20])
    stray = sorted(set(seen) - set(reference))
    if stray:
        problems.append(
            f"{len(stray)} test(s) ran that the collection does not hold, e.g. {stray[:5]}"
        )

    for shard in shard_dirs:
        if cases[shard] != len(selected[shard]):
            problems.append(
                f"{shard}: its JUnit XML holds {cases[shard]} test case(s) and its slice "
                f"{len(selected[shard])}, so the report and the slice disagree about what ran"
            )

    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected", type=int, required=True, help="how many shards ran")
    parser.add_argument("shard_dirs", type=Path, nargs="+", help="one directory per shard")
    args = parser.parse_args()

    problems = check(args.expected, args.shard_dirs)
    if problems:
        print(
            "FAIL: the sharded suite did not run the whole collection exactly once.",
            file=sys.stderr,
        )
        for problem in problems:
            print(f"  {problem}", file=sys.stderr)
        return 1

    total = sum(len(read_list(shard / SELECTED)) for shard in args.shard_dirs)
    print(
        f"OK: {len(args.shard_dirs)} shard(s) ran {total} test(s) between them, each exactly once."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
