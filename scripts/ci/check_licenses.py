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


def classify_body(text: str) -> tuple[str, str]:
    """The licence a *body* declares: the rule whose match appears earliest in it.

    Not the first rule in RULES that matches somewhere, which is what a body got
    when this branch was first written and which was a gate weakening. RULES is
    ordered so that narrower families are tried before wider ones — LGPL before
    GPL, Affero before either — and that ordering is right for an expression,
    where the string names one licence and nothing else. Across 18,000 characters
    of prose it stops meaning "the licence being declared" and starts meaning
    "whichever family the text happens to mention first in rule order".

    Measured, and this is why the function exists: the real GPL-2 says in its
    preamble that "other Free Software Foundation software is covered by the GNU
    Lesser General Public License instead". Under rule order that one sentence,
    eighteen lines in, outranked the title at the top, so a package shipping the
    full GPL-2 text classified `review` — an advisory that exits 0 — instead of
    `deny`. The same shape made the full GPL-3 report the Affero rule's reason,
    because its section 13 is headed "Use with the GNU Affero General Public
    License".

    **A licence text names itself before it mentions any other**, so position is
    the signal. It works within a single line as well as across a file, which is
    what keeps the narrower families winning: in "GNU AFFERO GENERAL PUBLIC
    LICENSE" the Affero rule matches at offset 4 and the GPL rule at offset 11,
    and in "GNU LESSER GENERAL PUBLIC LICENSE" the LGPL rule matches at 4 and the
    GPL rule at 11. Both are measured, and both are asserted in
    `scripts/ci/test_ci_scripts.py`.

    `<` below is strict, so an exact tie would go to the earlier rule in RULES.
    That is a choice about a case no pair of these patterns can produce — checked
    across the titles above and the short forms `AGPL-3.0`, `LGPL-3.0`, `GPL-3.0`
    and `MIT License`, no two rules match at the same offset — so it is written
    down as the conservative direction rather than claimed as a guarantee
    anything rests on.

    **This is not a conservative scan and must not be described as one.** It
    reports what a text declares. Two known-wrong answers on real texts, both
    predating this function and both left alone here because correcting them
    widens the gate further than this change is allowed to: the BSD text denies
    on the "All rights reserved" in its copyright line, which is in every
    BSD-family text by convention, and the MPL-2.0 text is `unknown` to the
    allow rule because that rule spells the version "License 2" and the text
    says "License Version 2.0". `scripts/ci/test_ci_scripts.py` records both so
    they cannot change without somebody noticing.
    """
    earliest: int | None = None
    found: tuple[str, str] | None = None
    for pattern, verdict, reason in RULES:
        match = re.search(pattern, text, re.IGNORECASE)
        if match is not None and (earliest is None or match.start() < earliest):
            earliest, found = match.start(), (verdict, reason)
    return found if found is not None else ("unknown", "unrecognized license string")


def classify(license_text: str) -> tuple[str, str]:
    """Return (verdict, reason) where verdict is allow | deny | review | unknown.

    Two shapes of input, told apart by whether the text contains a newline.

    An **expression** is resolved by its connector. "MIT OR GPL-3.0" is a
    choice, so we take the branch most favorable to us and call it allowed.
    "MIT AND GPL-3.0" is a conjunction — both sets of terms bind — so the worst
    branch decides.

    A **body** — the full licence text, which some packages put in the `License`
    field instead of an identifier — goes to `classify_body`, which takes the
    rule matching earliest in the text rather than the first rule that matches
    anywhere in it. A licence names itself before it mentions any other, and
    rule order across thousands of characters of prose picks the family the text
    mentions rather than the one it declares. Read that function before changing
    anything here: getting it wrong classified the full GPL-2 as `review`, which
    exits 0.

    It reports what a text **declares**, so it is not a conservative scan and the
    report should not be read as one. A body that declares MIT and mentions the
    GPL classifies allow, which is the right answer about the package and would
    be the wrong answer to "does anything here mention copyleft".
    """
    text = (license_text or "").strip()
    if not text:
        return "unknown", "no license metadata"

    # A licence *body* rather than an expression, handed to `classify_body`.
    #
    # `tiktoken` has no `License-Expression`; its `License` field is the full
    # 1078-character MIT text, copyright notice and all. Splitting that on its
    # connectors is meaningless — the word "and" appears in the prose, so the
    # text broke into six fragments, only the first of which named a licence,
    # and the conjunction rule then took the worst of them and answered unknown
    # about a plainly MIT package.
    #
    # **A newline is the whole test, and there is deliberately no length
    # threshold.** An SPDX expression is a single-line grammar, so no valid
    # expression contains a newline, and a threshold would be a tuning knob with
    # no correct value. Measured over the 99 packages installed here: exactly one
    # field contains a newline (tiktoken, 1078 characters) and the other 98 are
    # at most 36. A body flattened onto one line would still be split — and
    # still answer unknown, which is what it answers today, so that boundary
    # gives up nothing that currently works.
    #
    # What happens to it then is `classify_body`'s business, and the reason it is
    # a separate function with its own ordering is written there: rule order is
    # right for an expression and wrong for prose, and getting that wrong moved a
    # full GPL-2 text from `deny` to `review`.
    if "\n" in text:
        return classify_body(text)

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
