#!/usr/bin/env python3
"""Fail when the production bundle exceeds its stated budget.

Sizes are gzipped, which is what a browser actually downloads. The budget lives
in ci/bundle-budget.json so that raising it is a visible diff someone has to
justify in a pull request.

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

    if not args.dist.exists():
        print(f"note: {args.dist} does not exist — nothing built yet.")
        return 0

    budget = json.loads(args.budget.read_text())
    max_entry = int(budget["max_entry_js_gzip_bytes"])
    max_total = int(budget["max_initial_gzip_bytes"])

    js = sorted(args.dist.rglob("*.js"))
    css = sorted(args.dist.rglob("*.css"))

    if not js:
        print(f"note: no JavaScript found under {args.dist} — nothing to measure.")
        return 0

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
