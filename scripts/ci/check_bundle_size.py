#!/usr/bin/env python3
"""Fail when the production bundle exceeds its stated budget, or when there is none.

Sizes are gzipped, which is what a browser actually downloads. The budget lives
in ci/bundle-budget.json so that raising it is a visible diff someone has to
justify in a pull request.

**A missing build and a build with no JavaScript in it are refusals, and E1-04
is what made them so.** Both used to be notes that exited 0, which was the right
answer while the production build was still tolerant: there was nothing to
produce, so measuring nothing was honest and ADR 0002's notice said as much.
E1-04 makes that build enforcing, so from now on this script runs only ever
after a build that was required to succeed — and in that world "there is no
dist" and "the dist holds no JavaScript" are not facts about an absent frontend,
they are the two ways a build can appear to succeed and produce nothing. Exiting
0 on either is ADR 0083's "gate turned on and made meaningless", which that
record rejected in advance for this exact script.

The refusals print a sentence and exit 1. They do not raise: an uncaught
exception exits 1 too, and a checker that throws `FileNotFoundError` at a
missing directory satisfies "missing dist fails" while having no rule about
missing directories at all.

Usage:
    check_bundle_size.py frontend/dist --budget ci/bundle-budget.json
"""

from __future__ import annotations

import argparse
import gzip
import json
import sys
from pathlib import Path


def gzipped_size(path: Path) -> int:
    return len(gzip.compress(path.read_bytes(), compresslevel=9))


def human(n: int) -> str:
    return f"{n / 1024:.1f} KB"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dist", type=Path, help="Vite build output directory")
    parser.add_argument("--budget", type=Path, default=Path("ci/bundle-budget.json"))
    args = parser.parse_args()

    if not args.dist.is_dir():
        print(
            f"FAIL: {args.dist} is not a directory, so there is no build to measure.",
            file=sys.stderr,
        )
        print(
            "\n  The production build runs before this check and is required to succeed "
            "(E1-04), so a missing build output means the build wrote somewhere else or "
            "did not run at all. Run `npm run build --workspace frontend` first.",
            file=sys.stderr,
        )
        return 1

    budget = json.loads(args.budget.read_text())
    max_entry = int(budget["max_entry_js_gzip_bytes"])
    max_total = int(budget["max_initial_gzip_bytes"])

    js = sorted(args.dist.rglob("*.js"))
    css = sorted(args.dist.rglob("*.css"))

    if not js:
        print(f"FAIL: no JavaScript under {args.dist}, so nothing was measured.", file=sys.stderr)
        print(
            "\n  This is the shape a build leaves when its entry point moved, when it wrote "
            "to another directory, or when a plugin swallowed the bundle. It is not the same "
            "as a bundle that met its budget, and the two would be the same exit code if this "
            "passed.",
            file=sys.stderr,
        )
        return 1

    js_sizes = {p: gzipped_size(p) for p in js}
    css_total = sum(gzipped_size(p) for p in css)

    # The largest JS chunk stands in for the entry chunk. Good enough as a
    # regression tripwire, and it needs no build-tool integration.
    entry_path, entry_size = max(js_sizes.items(), key=lambda kv: kv[1])
    total = sum(js_sizes.values()) + css_total

    print(f"Bundle (gzipped), {len(js)} JS + {len(css)} CSS file(s):")
    print(f"  largest JS chunk : {human(entry_size)}  ({entry_path.name})")
    print(f"  budget           : {human(max_entry)}")
    print(f"  total initial    : {human(total)}")
    print(f"  budget           : {human(max_total)}")

    failures = []
    if entry_size > max_entry:
        failures.append(
            f"largest JS chunk {human(entry_size)} exceeds budget {human(max_entry)} "
            f"by {human(entry_size - max_entry)}"
        )
    if total > max_total:
        failures.append(
            f"total initial payload {human(total)} exceeds budget {human(max_total)} "
            f"by {human(total - max_total)}"
        )

    if failures:
        print("\nFAIL: bundle budget exceeded.", file=sys.stderr)
        for line in failures:
            print(f"  {line}", file=sys.stderr)
        print(
            "\n  Either trim the bundle, or raise the budget in "
            "ci/bundle-budget.json in this pull request and say why.",
            file=sys.stderr,
        )
        return 1

    print("\nOK: within budget.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
