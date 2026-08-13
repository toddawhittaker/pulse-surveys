#!/usr/bin/env python3
"""Self-test for the CI checker scripts. Run with plain python, no pytest.

These three scripts decide whether the build is allowed to go green, so a bug
in one of them is worse than a bug in most application code: it fails open and
nobody notices. They run before there is a test suite to hold them, which is
why they carry their own.

    python scripts/ci/test_ci_scripts.py
"""

from __future__ import annotations

import gzip
import json
import random
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

from check_licenses import classify  # noqa: E402

failures: list[str] = []


def check(label: str, got: object, want: object) -> None:
    if got != want:
        failures.append(f"{label}: got {got!r}, want {want!r}")


def run(script: str, *args: str) -> int:
    # S603: the command is this interpreter and a checker script from this
    # directory, both named in the source below. Nothing here comes from input.
    return subprocess.run(  # noqa: S603
        [sys.executable, str(HERE / script), *args],
        capture_output=True,
        text=True,
    ).returncode


# ---------------------------------------------------------------------------
# check_licenses.py
# ---------------------------------------------------------------------------
# The spelled-out forms matter as much as the SPDX ids: pip-licenses reports
# "GNU Affero General Public License v3" where npm reports "AGPL-3.0", and a
# pattern that only knows the short form lets the long one through as merely
# "unrecognized".
LICENSE_CASES = [
    ("MIT License", "allow"),
    ("MIT", "allow"),
    ("Mozilla Public License 2.0 (MPL 2.0)", "allow"),
    ("Apache Software License", "allow"),
    ("BSD-3-Clause", "allow"),
    ("Python Software Foundation License", "allow"),
    ("ISC", "allow"),
    # Denied — copyleft that reaches our source.
    ("GNU Affero General Public License v3", "deny"),
    ("AGPL-3.0", "deny"),
    ("AGPL-3.0-only", "deny"),
    ("GNU General Public License v3 (GPLv3)", "deny"),
    ("GPL-2.0", "deny"),
    # Denied — source-available, not open source.
    ("SSPL-1.0", "deny"),
    ("BUSL-1.1", "deny"),
    ("Elastic License 2.0", "deny"),
    ("CC-BY-NC-4.0", "deny"),
    # Weak copyleft: a human decides, because linkage is what matters.
    ("GNU Lesser General Public License v2 (LGPLv2)", "review"),
    ("GNU Library or Lesser General Public License (LGPL)", "review"),
    ("LGPL-3.0", "review"),
    ("GPL-2.0-with-classpath-exception", "review"),
    # Compound expressions.
    ("MIT OR Apache-2.0", "allow"),
    ("MIT OR GPL-2.0", "allow"),  # a choice — we take MIT
    ("MIT AND GPL-3.0", "deny"),  # a conjunction — both sets of terms bind
    ("(MIT OR CC0-1.0)", "allow"),
    # No usable metadata.
    ("UNKNOWN", "unknown"),
    ("", "unknown"),
    ("Weird Custom License", "unknown"),
]

for text, want in LICENSE_CASES:
    check(f"classify({text!r})", classify(text)[0], want)

with tempfile.TemporaryDirectory() as tmp:
    d = Path(tmp)

    (d / "clean.json").write_text(
        json.dumps([{"Name": "fastapi", "Version": "0.115.0", "License": "MIT License"}])
    )
    check(
        "licenses: clean tree exits 0",
        run("check_licenses.py", "--python-json", str(d / "clean.json")),
        0,
    )

    (d / "agpl.json").write_text(
        json.dumps(
            [{"Name": "bad", "Version": "1.0", "License": "GNU Affero General Public License v3"}]
        )
    )
    check(
        "licenses: AGPL fails the build",
        run("check_licenses.py", "--python-json", str(d / "agpl.json")),
        1,
    )

    (d / "npm.json").write_text(json.dumps({"mongo@1.0.0": {"licenses": "SSPL-1.0"}}))
    check(
        "licenses: SSPL fails the build",
        run("check_licenses.py", "--npm-json", str(d / "npm.json")),
        1,
    )

    check("licenses: nothing to scan exits 0", run("check_licenses.py"), 0)

    # -----------------------------------------------------------------------
    # check_invariants.py
    # -----------------------------------------------------------------------
    def junit(path: Path, cases: str) -> str:
        path.write_text(f'<testsuites><testsuite name="pytest">{cases}</testsuite></testsuites>')
        return str(path)

    passing = junit(
        d / "pass.xml",
        '<testcase classname="t" name="test_student_sees_no_benchmark"/>'
        '<testcase classname="t" name="test_sibling_lead_isolated"/>',
    )
    check("invariants: all ran", run("check_invariants.py", passing), 0)

    skipped = junit(
        d / "skip.xml",
        '<testcase classname="t" name="test_a"/>'
        '<testcase classname="t" name="test_small_n"><skipped message="flaky"/></testcase>',
    )
    check("invariants: a skip is a failure", run("check_invariants.py", skipped), 1)
    check(
        "invariants: --allow-empty does not excuse a skip",
        run("check_invariants.py", skipped, "--allow-empty"),
        1,
    )

    failing = junit(
        d / "fail.xml",
        '<testcase classname="t" name="test_a"><failure message="boom"/></testcase>',
    )
    check("invariants: a failure is a failure", run("check_invariants.py", failing), 1)

    empty = junit(d / "empty.xml", "")
    check("invariants: empty suite fails by default", run("check_invariants.py", empty), 1)
    check(
        "invariants: empty suite tolerated with flag",
        run("check_invariants.py", empty, "--allow-empty"),
        0,
    )
    check(
        "invariants: missing file fails by default",
        run("check_invariants.py", str(d / "nope.xml")),
        1,
    )
    check(
        "invariants: missing file tolerated with flag",
        run("check_invariants.py", str(d / "nope.xml"), "--allow-empty"),
        0,
    )

    # -----------------------------------------------------------------------
    # check_bundle_size.py
    # -----------------------------------------------------------------------
    budget = d / "budget.json"
    budget.write_text(json.dumps({"max_entry_js_gzip_bytes": 4096, "max_initial_gzip_bytes": 8192}))

    dist = d / "dist"
    (dist / "assets").mkdir(parents=True)
    # Random-ish bytes so gzip cannot collapse them to nothing.
    small = bytes(range(256)) * 8  # ~2 KB raw, compresses well under budget
    (dist / "assets" / "index-abc.js").write_bytes(small)
    check(
        "bundle: within budget exits 0",
        run("check_bundle_size.py", str(dist), "--budget", str(budget)),
        0,
    )

    # Seeded, so the fixture is deterministic, but effectively incompressible —
    # a structured byte pattern gzips down below the budget and makes the
    # assertion vacuous.
    # S311: this is test data, not a key. A seeded generator is exactly right.
    big = random.Random(20260812).randbytes(120_000)  # noqa: S311
    (dist / "assets" / "vendor-def.js").write_bytes(big)
    check(
        "bundle: over budget exits 1",
        run("check_bundle_size.py", str(dist), "--budget", str(budget)),
        1,
    )

    check(
        "bundle: missing dist exits 0",
        run("check_bundle_size.py", str(d / "no-dist"), "--budget", str(budget)),
        0,
    )

    # Sanity: the oversized fixture really is oversized after gzip, so the
    # assertion above is testing the budget and not a quirk of compression.
    if len(gzip.compress(big, compresslevel=9)) <= 4096:
        failures.append("bundle: fixture compressed below the budget; test is vacuous")

# ---------------------------------------------------------------------------
total = len(LICENSE_CASES) + 15
if failures:
    print(f"FAIL: {len(failures)} of {total} checks failed:", file=sys.stderr)
    for line in failures:
        print(f"  {line}", file=sys.stderr)
    sys.exit(1)

print(f"OK: {total} checks passed.")
