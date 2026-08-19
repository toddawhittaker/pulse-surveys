#!/usr/bin/env python3
"""Assert that the SPEC §4.1 invariant suite actually ran.

The §4.1 invariants are assertions about what a student can never see. In a
green checkmark, a skipped invariant test looks exactly like a passing one, and
a deleted invariant test looks exactly like a suite that never had it. This
checker closes that gap: for the invariant suite, a skip is a failure, an xfail
is a failure, and collecting nothing at all is a failure.

**This is one half of the gate, and it cannot see the other half's subject.** It
reads the JUnit XML a run produced, which carries no assertion count, so a marked
test that ran and asserted nothing is counted toward the "N invariant test(s)
ran" printed below. `check_invariant_assertions.py` reads the sources and refuses
exactly that (E0-36 item 3). Both callers run both, in that order.

Usage:
    check_invariants.py reports/invariants.xml
    check_invariants.py reports/invariants.xml --allow-empty   # nothing passes this

`--allow-empty` existed so that the gate could ship before there was anything for
it to check. E0-10 landed the first §4.1 invariants and took the flag out of both
callers, so neither `.github/workflows/ci.yml` nor the `Makefile` passes it and
`tests/unit/test_invariant_gate_is_strict.py` fails if either starts again. The
option stays here because removing it would be a change to this checker's
behaviour dressed up as tidying, and because the tolerance is a caller's decision
to justify rather than a capability to delete.
"""

from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("junit_xml", type=Path, help="pytest --junitxml output")
    parser.add_argument(
        "--allow-empty",
        action="store_true",
        help=(
            "Tolerate a suite that collected zero invariant tests. The first "
            "§4.1 invariants landed in E0-10 and no caller in this repository "
            "passes this any more; passing it again is a decision to say out "
            "loud in the pull request that does it."
        ),
    )
    args = parser.parse_args()

    if not args.junit_xml.exists():
        if args.allow_empty:
            print(
                f"note: {args.junit_xml} not written — no invariant run to read.\n"
                "      Tolerated because --allow-empty was passed. No caller in "
                "this repository passes it since E0-10."
            )
            return 0
        print(
            f"FAIL: {args.junit_xml} was not written. The invariant suite did not run.",
            file=sys.stderr,
        )
        return 1

    # S314: the input is the JUnit XML pytest just wrote in this job, not
    # anything a user supplied. defusedxml would add a dependency to a script
    # that must run before any dependency is installed.
    root = ET.parse(args.junit_xml).getroot()  # noqa: S314
    cases = root.iter("testcase")

    total = 0
    skipped: list[str] = []
    failed: list[str] = []

    for case in cases:
        total += 1
        name = f"{case.get('classname', '')}::{case.get('name', '')}"
        # pytest records both skip and xfail as <skipped> in JUnit XML. Both
        # mean the assertion did not execute, which is what we are policing.
        if case.find("skipped") is not None:
            skipped.append(name)
        if case.find("failure") is not None or case.find("error") is not None:
            failed.append(name)

    if total == 0:
        if args.allow_empty:
            print(
                "note: the invariant suite collected 0 tests.\n"
                "      Tolerated because --allow-empty was passed. No caller in "
                "this repository passes it since E0-10."
            )
            return 0
        print(
            "FAIL: the invariant suite collected 0 tests. The §4.1 invariants "
            "must run on every pipeline.",
            file=sys.stderr,
        )
        return 1

    problems = False

    if skipped:
        problems = True
        print(
            f"FAIL: {len(skipped)} invariant test(s) did not execute. A skipped "
            "or xfailed invariant is a failure, not a skip — see CLAUDE.md.",
            file=sys.stderr,
        )
        for name in skipped:
            print(f"  skipped: {name}", file=sys.stderr)

    if failed:
        problems = True
        print(f"FAIL: {len(failed)} invariant test(s) failed.", file=sys.stderr)
        for name in failed:
            print(f"  failed: {name}", file=sys.stderr)

    if problems:
        return 1

    print(f"OK: {total} invariant test(s) ran, none skipped, none failed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
