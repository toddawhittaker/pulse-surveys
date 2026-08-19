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
    # `\bCNRI\b` is here for `regex`, which declares `Apache-2.0 AND
    # CNRI-Python`. That is a well-formed SPDX expression and the split handled
    # it correctly; the failure was that no rule knew the second term, so a
    # conjunction of two permissive licences resolved to unknown. CNRI-Python is
    # the Python 1.6 licence from the same chain as the PSF one — permissive,
    # with attribution and a Virginia choice-of-law clause. That clause is why
    # it is called GPL-incompatible, which is a different question from whether
    # we may ship it under MIT (SPEC §10), and the answer to this one is yes.
    #
    # Deliberately not reached for `CNRI-Python-GPL-Compatible`: the deny rule
    # for `\bGPL` sits above this and matches it first. That is the conservative
    # answer for a licence this project has never depended on, and widening it
    # is not this change's business.
    (r"Python Software Foundation|\bPSF\b|\bCNRI\b", "allow", "permissive"),
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

    Two shapes of input, told apart by whether the text contains a newline.

    An **expression** is resolved by its connector. "MIT OR GPL-3.0" is a
    choice, so we take the branch most favorable to us and call it allowed.
    "MIT AND GPL-3.0" is a conjunction — both sets of terms bind — so the worst
    branch decides.

    A **body** — the full licence text, which some packages put in the `License`
    field instead of an identifier — is scanned whole against RULES in order,
    with no splitting. See the comment below for why that is safe and why the
    test is a newline.

    One imprecision worth knowing when reading a report: scanning a body whole
    attributes the verdict to the first rule that matches anywhere in it, and a
    licence text may *mention* another licence. The full GPL-3 body denies with
    the Affero rule's reason, because its section 13 is headed "Use with the GNU
    Affero General Public License". The verdict is right and conservative; only
    the reason names the wrong family. Narrowing that would mean deciding which
    mention is the declaration, which is a larger change than this one and buys
    a better message rather than a better answer.
    """
    text = (license_text or "").strip()
    if not text:
        return "unknown", "no license metadata"

    # A licence *body* rather than an expression, and it is scanned whole.
    #
    # `tiktoken` has no `License-Expression`; its `License` field is the full
    # 1078-character MIT text, copyright notice and all. Splitting that on its
    # connectors is meaningless — the word "and" appears in the prose, so the
    # text broke into six fragments, only the first of which named a licence,
    # and the conjunction rule then took the worst of them and answered unknown
    # about a plainly MIT package.
    #
    # **What makes the unsplit scan safe is the order of RULES**, not this
    # condition: every deny and review rule sits above every allow rule, and
    # `classify_single` is first-match-wins, so scanning a whole body reaches a
    # deny before it can reach a permissive word that happens to appear in the
    # prose. A full GPL body hits "General Public License" and denies; a full
    # AGPL body hits "Affero" first and denies for that reason. Reordering RULES
    # to put an allow rule above a deny rule turns this line into a hole, which
    # is why the ordering comment above RULES says what it says.
    #
    # A newline is the whole test, and there is deliberately no length
    # threshold. An SPDX expression is a single-line grammar, so no valid
    # expression contains a newline, and a threshold would be a tuning knob with
    # no correct value. Measured over the 99 packages installed here: exactly one
    # field contains a newline (tiktoken, 1078 characters) and the other 98 are
    # at most 36. A body flattened onto one line would still be split — and
    # still answer unknown, which is what it answers today, so that boundary
    # gives up nothing that currently works.
    if "\n" in text:
        return classify_single(text)

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
