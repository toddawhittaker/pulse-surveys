#!/usr/bin/env python3
"""Self-test for the CI checker scripts. Run with plain python, no pytest.

These scripts decide whether the build is allowed to go green, so a bug in one
of them is worse than a bug in most application code: it fails open and nobody
notices. They run before there is a test suite to hold them, which is why they
carry their own. No count of them here: E0-36 added a fourth and this sentence
said three, which is `docs/MISTAKES.md` entry 1 arriving through arithmetic.

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

    # -----------------------------------------------------------------------
    # check_invariant_assertions.py
    # -----------------------------------------------------------------------
    # E0-36 item 3. The rule: an `invariant`-marked test's own body must contain
    # an `assert`, a `with pytest.raises(...)` block, or a `pytest.fail(...)`
    # call. A body whose only statements are calls is refused, and a helper the
    # test calls is not chased.
    #
    # `tests/unit/test_the_invariant_gate_refuses_a_test_that_asserts_nothing.py`
    # asserts the same rule from the other side of the test wall, written from
    # the ticket rather than from this implementation. What is here and not there
    # is everything that is a property of *this* checker rather than of the rule:
    # the two ways pytest marks a test, an empty scan, an unparseable file, and a
    # path that is not there.
    def planted(name: str, source: str) -> str:
        """Write one sample as the only test file in a directory of its own.

        One directory per sample, because the verdict is per run: a checker
        handed two samples at once answers about the pair.
        """
        directory = d / "invariant-samples" / name
        directory.mkdir(parents=True)
        (directory / "test_planted.py").write_text(source.lstrip("\n"))
        return str(directory)

    def verdict(directory: str, refusing: str = "") -> object:
        """What the checker did with one sample: an exit status, or a status and an attribution.

        **Why a refusal is not read as an exit code alone.** This checker exits 1
        for three different reasons — the rule refused a test, it found no marked
        test at all, and it could not parse a file — so `== 1` on a sample that
        should be refused is satisfied by a checker that never saw the marker.
        That is not hypothetical: two samples below were added to kill a mutation
        that reads only the first decorator, they were written expecting 1, and
        they passed under the mutation because a checker blind to the marker
        reports an empty scan, which is also 1. `docs/MISTAKES.md` entry 3.

        So a refusal is checked as the pair (1, the test was named), which only a
        checker that read the body and applied the rule can produce, and an
        allowance is checked as 0, which only a checker that found a marked test
        and was satisfied by it can produce. Passing `refusing` asks for the pair.
        """
        # S603: the command is this interpreter and a checker script from this
        # directory. The only argument is a directory this file just wrote.
        completed = subprocess.run(  # noqa: S603
            [sys.executable, str(HERE / "check_invariant_assertions.py"), directory],
            capture_output=True,
            text=True,
        )
        if not refusing:
            return completed.returncode
        return (completed.returncode, refusing in completed.stdout + completed.stderr)

    REFUSED = (1, True)
    MARKED = "import pytest\n\n\n@pytest.mark.invariant\n"

    check(
        "invariant assertions: an assert in the body is allowed",
        verdict(planted("assert", MARKED + "def test_a(x):\n    assert x.visible == []\n")),
        0,
    )
    check(
        "invariant assertions: a body that ends after a call is refused",
        verdict(
            planted("call-only", MARKED + "def test_b(x):\n    x.section_responses()\n"), "test_b"
        ),
        REFUSED,
    )
    check(
        "invariant assertions: a pytest.raises body is allowed",
        verdict(
            planted(
                "raises",
                MARKED
                + "def test_c(x):\n    with pytest.raises(PermissionError):\n        x.read()\n",
            )
        ),
        0,
    )
    check(
        "invariant assertions: a pytest.fail body is allowed",
        verdict(
            planted(
                "fail",
                MARKED + 'def test_d(x):\n    if x.care:\n        pytest.fail("reachable")\n',
            )
        ),
        0,
    )
    # The discriminating sample. The helper *does* assert, so a checker that
    # searched the module rather than the body would allow this — and would allow
    # the planted fixture this item came from whenever a helper sat above it.
    check(
        "invariant assertions: an assertion inside a helper it calls is refused",
        verdict(
            planted(
                "helper",
                "import pytest\n\n\ndef refuses(action):\n    assert action() is None\n\n\n"
                "@pytest.mark.invariant\ndef test_e(g):\n    refuses(g.assign)\n",
            ),
            "test_e",
        ),
        REFUSED,
    )
    # How `tests/integration/test_identity_grants.py` writes every one of its
    # refusals. A checker reading only the top level of a body is red against the
    # suite it guards.
    check(
        "invariant assertions: an assert nested in a with and a for is allowed",
        verdict(
            planted(
                "nested",
                MARKED + "def test_f(s):\n    with acting_as(s):\n        for v in views(s):\n"
                "            assert refused(s, v)\n",
            )
        ),
        0,
    )
    # `tests/integration/test_role_assignment_graph.py` stacks the marker with
    # `parametrize`, marker first.
    check(
        "invariant assertions: a second decorator does not hide the marker",
        verdict(
            planted(
                "stacked",
                "import pytest\n\n\n@pytest.mark.invariant\n"
                '@pytest.mark.parametrize("kind", ["prefix"])\n'
                "def test_g(g, kind):\n    g.assign(kind)\n",
            ),
            "test_g",
        ),
        REFUSED,
    )
    # The same pair the other way up, and the body asserts on purpose: the
    # question here is whether the marker is *seen* below another decorator, and
    # only an exit of 0 answers it. Written first as a refusal expecting 1, it
    # passed under a checker that read `decorator_list[:1]` — because a checker
    # blind to the marker reports an empty scan, which is 1 as well. pytest does
    # not care about decorator order, so a checker that does would go blind the
    # first time somebody wrote `parametrize` on top, silently.
    check(
        "invariant assertions: the marker is seen below another decorator",
        verdict(
            planted(
                "stacked-other-way",
                'import pytest\n\n\n@pytest.mark.parametrize("kind", ["prefix"])\n'
                "@pytest.mark.invariant\n"
                "def test_g2(g, kind):\n    assert g.assign(kind) is None\n",
            )
        ),
        0,
    )
    # A marked test inside a `Test*` class, asserting for the same reason: an
    # exit of 0 is the only verdict that says the checker descended into the
    # class and found it. Nothing in this repository is written that way, and the
    # checker descends anyway because pytest collects them — so the shape is
    # asserted here rather than left as code no sample exercises.
    check(
        "invariant assertions: a marked test inside a class is seen",
        verdict(
            planted(
                "in-a-class",
                "import pytest\n\n\nclass TestPurview:\n    @pytest.mark.invariant\n"
                "    def test_g3(self, g):\n        assert g.purview() == []\n",
            )
        ),
        0,
    )
    # The other way pytest marks a test, and the reason it is here: three real
    # §4.1 invariants in
    # `tests/unit/test_no_service_reads_an_identity_table_directly.py` are marked
    # this way and by no decorator anywhere. A checker that knew only the
    # decorator would report a clean scan over all three.
    PYTESTMARK = "import pytest\n\npytestmark = pytest.mark.invariant\n\n\n"
    check(
        "invariant assertions: a module-level pytestmark marks a body that asserts",
        verdict(planted("pytestmark-ok", PYTESTMARK + "def test_h(x):\n    assert x.rows == []\n")),
        0,
    )
    check(
        "invariant assertions: a module-level pytestmark refuses a call-only body",
        verdict(planted("pytestmark-bad", PYTESTMARK + "def test_i(x):\n    x.rows()\n"), "test_i"),
        REFUSED,
    )
    # The rule's subject is marked tests. An unmarked test that asserts nothing is
    # most of the suite and every helper in it.
    check(
        "invariant assertions: an unmarked test that asserts nothing is not the subject",
        verdict(
            planted(
                "unmarked",
                MARKED
                + "def test_j(x):\n    assert x.ok\n\n\ndef test_k(seed):\n    seed.load()\n",
            )
        ),
        0,
    )
    # An empty scan is a failure for the reason its sibling gives about an empty
    # collection: an exit of 0 cannot distinguish "every marked test asserts" from
    # "the marker was renamed and this read nothing".
    check(
        "invariant assertions: finding no marked test at all is a failure",
        verdict(planted("none", "def test_l(x):\n    x.run()\n")),
        1,
    )
    # Red rather than skipped. A file this cannot parse is a file whose invariants
    # it has not read.
    check(
        "invariant assertions: a file that cannot be parsed is a failure",
        verdict(planted("unparseable", "def test_m(:\n")),
        1,
    )
    check(
        "invariant assertions: a path that does not exist is a failure",
        verdict(str(d / "no-such-directory")),
        1,
    )
    # The positive control, and the only check here that runs the checker against
    # what it actually guards: every §4.1 invariant in this repository satisfies
    # the rule today. Without it the fifteen above prove the checker works on
    # samples and say nothing about whether the gate it was wired into is green.
    check(
        "invariant assertions: the real invariant suite satisfies the rule",
        verdict(str(HERE.parent.parent / "tests")),
        0,
    )

# ---------------------------------------------------------------------------
total = len(LICENSE_CASES) + 15 + 16
if failures:
    print(f"FAIL: {len(failures)} of {total} checks failed:", file=sys.stderr)
    for line in failures:
        print(f"  {line}", file=sys.stderr)
    sys.exit(1)

print(f"OK: {total} checks passed.")
