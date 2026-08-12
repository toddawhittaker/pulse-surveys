#!/usr/bin/env python3
"""Fail on dependencies whose licenses are incompatible with MIT distribution.

SPEC §10 requires that everything shipped is compatible with distributing this
project under MIT. Strong copyleft and source-available licenses are not, so
they break the build rather than becoming a note for the E13 license sweep.

Reads pip-licenses JSON and/or license-checker-rseidelsohn JSON:

    check_licenses.py --python-json reports/py-licenses.json \
                      --npm-json reports/npm-licenses.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# Rules are evaluated in order and the first match wins, which is what makes
# the family distinctions work: "GNU Lesser General Public License" has to be
# recognized as LGPL before anything looks for "General Public License", and
# "Affero" has to be caught before either. Patterns match both the SPDX
# identifier and the spelled-out name, because pip-licenses reports the long
# form ("GNU Affero General Public License v3") while npm reports the short one
# ("AGPL-3.0"). Matching only the short form is how an AGPL dependency slips
# through as "unrecognized".
RULES: list[tuple[str, str, str]] = [
    # --- denied: copyleft that reaches our source -------------------------
    (r"\bAGPL|Affero", "deny", "network copyleft — reaches our source"),
    # --- review: weak copyleft, before the general GPL rule below ---------
    (
        r"\bLGPL|Lesser General Public|Library General Public",
        "review",
        "weak copyleft — linkage matters",
    ),
    (r"Classpath[- ]exception|GPL.*Classpath", "review", "GPL with linking exception"),
    (r"\bCDDL|Common Development and Distribution", "review", "file-level copyleft"),
    (r"\bEUPL|European Union Public", "review", "copyleft with compatibility list"),
    # --- denied: strong copyleft ------------------------------------------
    (r"\bGPL|General Public License", "deny", "strong copyleft — reaches our source"),
    # --- denied: source-available, not open source ------------------------
    (r"\bSSPL|Server Side Public", "deny", "source-available, not OSI-approved"),
    (r"\bBUSL|\bBSL\b|Business Source", "deny", "source-available, not OSI-approved"),
    (r"Elastic License|\bELv2", "deny", "source-available, not OSI-approved"),
    (r"CC-BY-NC|NonCommercial|Non-Commercial", "deny", "non-commercial restriction"),
    (r"Commons Clause", "deny", "non-commercial restriction"),
    (r"\bProprietary|\bCommercial\b|All Rights Reserved", "deny", "not redistributable"),
    # --- allowed: permissive, or copyleft confined to its own files -------
    # MPL-2.0 and EPL-2.0 require sharing changes to *their* files only, which
    # is compatible with shipping this project under MIT.
    (r"\bMIT\b|\bExpat\b", "allow", "permissive"),
    (r"\bBSD\b|\bBSD-[0234]", "allow", "permissive"),
    (r"\bApache\b", "allow", "permissive"),
    (r"\bISC\b", "allow", "permissive"),
    (r"Python Software Foundation|\bPSF\b", "allow", "permissive"),
    (r"\bMPL[- ]?2|Mozilla Public License 2", "allow", "file-level copyleft"),
    (r"\bEPL[- ]?2|Eclipse Public License 2", "allow", "file-level copyleft"),
    (r"\bUnlicense\b|\bCC0\b|Public Domain|\bWTFPL\b", "allow", "public domain"),
    (r"\bZlib\b|\bHPND\b|\bBlueOak|Artistic[- ]?2", "allow", "permissive"),
]

# Worst-to-best, for combining the parts of a compound license expression.
SEVERITY = {"deny": 3, "unknown": 2, "review": 1, "allow": 0}


def classify_single(text: str) -> tuple[str, str]:
    text = text.strip().strip("()").strip()
    if not text or text.upper() in {"UNKNOWN", "UNLICENSED", "NONE", "SEE LICENSE"}:
        return "unknown", "no license metadata"
    for pattern, verdict, reason in RULES:
        if re.search(pattern, text, re.IGNORECASE):
            return verdict, reason
    return "unknown", "unrecognized license string"


def classify(license_text: str) -> tuple[str, str]:
    """Return (verdict, reason) where verdict is allow | deny | review | unknown.

    Compound expressions are resolved by their connector. "MIT OR GPL-3.0" is
    a choice, so we take the branch most favorable to us and call it allowed.
    "MIT AND GPL-3.0" is a conjunction — both sets of terms bind — so the worst
    branch decides.
    """
    text = (license_text or "").strip()
    if not text:
        return "unknown", "no license metadata"

    if re.search(r"\bAND\b", text, re.IGNORECASE):
        parts = re.split(r"\bAND\b", text, flags=re.IGNORECASE)
        results = [classify_single(p) for p in parts if p.strip()]
        return max(results, key=lambda r: SEVERITY[r[0]]) if results else ("unknown", "empty")

    parts = re.split(r"\s+OR\s+|\s*/\s*|\s*[;,]\s*|\s*\|\s*", text)
    results = [classify_single(p) for p in parts if p.strip()]
    return min(results, key=lambda r: SEVERITY[r[0]]) if results else ("unknown", "empty")


def load_python(path: Path) -> list[tuple[str, str]]:
    data = json.loads(path.read_text())
    return [
        (f"{row.get('Name', '?')}@{row.get('Version', '?')}", row.get("License", ""))
        for row in data
    ]


def load_npm(path: Path) -> list[tuple[str, str]]:
    data = json.loads(path.read_text())
    return [(name, row.get("licenses", "")) for name, row in data.items()]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python-json", type=Path, help="pip-licenses --format=json")
    parser.add_argument("--npm-json", type=Path, help="license-checker --json")
    parser.add_argument(
        "--strict-unknown",
        action="store_true",
        help="Fail on packages with no recognizable license metadata.",
    )
    args = parser.parse_args()

    packages: list[tuple[str, str]] = []
    if args.python_json and args.python_json.exists():
        packages += load_python(args.python_json)
    if args.npm_json and args.npm_json.exists():
        packages += load_npm(args.npm_json)

    if not packages:
        print("note: no dependency manifests to scan.")
        return 0

    denied: list[str] = []
    review: list[str] = []
    unknown: list[str] = []

    for name, license_text in packages:
        verdict, reason = classify(license_text)
        if verdict == "deny":
            denied.append(f"  {name}: {license_text} — {reason}")
        elif verdict == "review":
            review.append(f"  {name}: {license_text} — {reason}")
        elif verdict == "unknown":
            unknown.append(f"  {name}: {license_text or '(none)'} — {reason}")

    print(f"Scanned {len(packages)} package(s).")

    if review:
        print(f"\n{len(review)} package(s) need a human look (weak copyleft):")
        print("\n".join(review))
        print("  Compatible if dynamically linked; not if vendored or statically linked.")

    if unknown:
        print(f"\n{len(unknown)} package(s) have no recognizable license:")
        print("\n".join(unknown))
        if args.strict_unknown:
            denied += unknown

    if denied:
        sys.stdout.flush()  # keep the report above the failure, not interleaved
        print(
            f"\nFAIL: {len(denied)} package(s) are incompatible with MIT "
            "distribution (SPEC §10):",
            file=sys.stderr,
        )
        print("\n".join(denied), file=sys.stderr)
        return 1

    print("\nOK: no license incompatible with MIT distribution.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
