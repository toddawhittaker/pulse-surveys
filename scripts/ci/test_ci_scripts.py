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
    # E0-29 item 4b. `regex` declares this, and it is a well-formed expression
    # the split always handled correctly — what was missing was any rule for the
    # second term, so a conjunction of two permissive licences came out unknown.
    ("Apache-2.0 AND CNRI-Python", "allow"),
    ("CNRI-Python", "allow"),
    # The word boundary in the `\bMIT\b` rule, asserted rather than assumed. It
    # exists to catch the widening E0-29 item 4b was told not to make: a blanket
    # `MIT` rule with no boundary, which allows anything containing those three
    # letters. "Transmittal" is the cheapest string that tells the two apart, and
    # `classify_body` does not cover this — under earliest-match a blanket rule
    # only bites when the substring precedes the declaring line, which in a real
    # licence text it does not.
    ("Transmittal License", "unknown"),
    # Still denied, and it is the near miss for the rule above: the `\bGPL` deny
    # rule sits higher than the permissive one that now knows CNRI.
    ("CNRI-Python-GPL-Compatible", "deny"),
    # No usable metadata.
    ("UNKNOWN", "unknown"),
    ("", "unknown"),
    ("Weird Custom License", "unknown"),
]

for text, want in LICENSE_CASES:
    check(f"classify({text!r})", classify(text)[0], want)

# ---------------------------------------------------------------------------
# check_licenses.py — licence *bodies* rather than expressions (E0-29 item 4b)
# ---------------------------------------------------------------------------
# Some packages put the whole licence text in the `License` metadata field
# instead of an identifier. `classify()` used to split every input on its
# connectors, and the word "and" occurs in licence prose, so a body broke into
# fragments that named nothing and the conjunction rule answered `unknown` about
# a plainly permissive package. Bodies are told apart by containing a newline and
# handed to `classify_body`.
#
# **Every case asserts the reason as well as the verdict**, and on this function
# that is the whole point rather than thoroughness. `classify_body` takes the
# rule matching *earliest in the text* rather than the first rule in RULES that
# matches anywhere, and several bodies below deny either way — so a verdict alone
# cannot see the ordering it depends on. The first version of this section
# asserted verdicts over hand-written fixtures and missed that the real GPL-2
# classified `review`.
#
# **The bodies are real text, cut to the smallest excerpt that carries both the
# declaring line and the phrase that used to trap it.** Each was verified to
# produce the same verdict *and* reason as the full file it came from before
# being pasted here. They are pasted rather than read from
# /usr/share/common-licenses at run time, because a fixture reading a path
# outside the repository passes vacuously everywhere that path is absent, which
# is every CI runner. The two constructed ones say so.

# tiktoken's `License` field exactly as its installed metadata carries it: the
# full MIT licence, 1078 characters, and the reason this item exists.
TIKTOKEN_LICENSE_BODY = (
    "MIT License\n"
    "\n"
    "Copyright (c) 2022 OpenAI, Shantanu Jain\n"
    "\n"
    "Permission is hereby granted, free of charge, to any person obtaining a copy\n"
    'of this software and associated documentation files (the "Software"), to deal\n'
    "in the Software without restriction, including without limitation the rights\n"
    "to use, copy, modify, merge, publish, distribute, sublicense, and/or sell\n"
    "copies of the Software, and to permit persons to whom the Software is\n"
    "furnished to do so, subject to the following conditions:\n"
    "\n"
    "The above copyright notice and this permission notice shall be included in all\n"
    "copies or substantial portions of the Software.\n"
    "\n"
    'THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR\n'
    "IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,\n"
    "FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE\n"
    "AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER\n"
    "LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,\n"
    "OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE\n"
    "SOFTWARE.\n"
    ""
)

# The real GPL-2, /usr/share/common-licenses/GPL-2: its title line, and line 18
# of its preamble. **This is the regression case.** That line says other FSF
# software "is covered by the GNU Lesser General Public License instead", and
# because the LGPL rule sits above the GPL rule in RULES, a scan that took the
# first matching rule classified the whole 18,092-character text as `review` —
# which prints a note and exits 0. A package shipping the GPL-2 passed the build.
GPL2_LICENSE_BODY = (
    "GNU GENERAL PUBLIC LICENSE\n"
    "the GNU Lesser General Public License instead.)  You can apply it to\n"
    ""
)

# The real GPL-3: its title line, and the heading of section 13, 552 lines in.
# Catches the same defect in the other direction — the verdict was right and the
# *reason* named Affero, because that rule sits above the GPL rule too.
GPL3_LICENSE_BODY = (
    "GNU GENERAL PUBLIC LICENSE\n" "13. Use with the GNU Affero General Public License.\n" ""
)

# The real LGPL-3 title line, which contains both "LESSER GENERAL PUBLIC" and,
# four words later, "GENERAL PUBLIC LICENSE". Earliest-match must not turn into
# "whichever rule matches at the lowest offset regardless of specificity": both
# match inside this one line and LGPL starts first, so it stays `review`.
LGPL3_LICENSE_BODY = "GNU LESSER GENERAL PUBLIC LICENSE\n" ""

# The real Apache-2.0: its title line, and the limitation-of-liability clause
# 163 lines in that says "other commercial damages or losses". The
# `\bCommercial\b` deny rule matches that phrase, so under rule order the whole
# Apache-2.0 text denied — a false deny on one of the most common permissive
# licences, and it predates this change.
APACHE2_LICENSE_BODY = (
    "Apache License\n" "other commercial damages or losses), even if such Contributor\n" ""
)

# The real AGPL-3 preamble, from Debian's libgs-common copyright file, which
# encodes a blank line as a lone "." — removing that is decoding, not editing.
# `Affero` matches at offset 4 of the title and `General Public License` at
# offset 11, so this pins position ordering working *within a single line* — not
# a tie-break, which no pair of these patterns can produce.
AGPL3_LICENSE_BODY = (
    "GNU AFFERO GENERAL PUBLIC LICENSE\n"
    "Version 3, 19 November 2007\n"
    "\n"
    "Copyright (C) 2007 Free Software Foundation, Inc. <http://fsf.org/>\n"
    "Everyone is permitted to copy and distribute\n"
    "verbatim copies of this license document,\n"
    "but changing it is not allowed.\n"
    "\n"
    "Preamble\n"
    "\n"
    "The GNU Affero General Public License is a free, copyleft license\n"
    "for software and other kinds of works,\n"
    "specifically designed to ensure cooperation with the community\n"
    "in the case of network server software.\n"
    "\n"
    "The licenses for most software and other practical works\n"
    "are designed to take away your freedom to share and change the works.\n"
    "By contrast, our General Public Licenses are intended\n"
    "to guarantee your freedom to share\n"
    "and change all versions of a program--\n"
    "to make sure it remains free software for all its users.\n"
    ""
)

# **Recorded, not endorsed.** The real BSD text denies, on the "All rights
# reserved" in its copyright line, which is in every BSD-family text by
# convention — and its first line names no licence at all. The real MPL-2.0
# denies because the allow rule spells the version "License 2" while the text
# says "License Version 2.0", so the earliest thing that does match is its
# reference to the GNU GPL. Both are wrong, both predate this change and are
# unchanged by it, and correcting them means widening the gate further than
# E0-29 item 4b is allowed to. They are asserted so that the body path's real
# behaviour is written down where somebody will see it, and so neither can drift
# without a test saying so.
BSD_LICENSE_BODY = (
    "Copyright (c) The Regents of the University of California.\n" "All rights reserved.\n" ""
)

MPL2_LICENSE_BODY = (
    "Mozilla Public License Version 2.0\n"
    "means either the GNU General Public License, Version 2.0, the GNU\n"
    ""
)

# Constructed, not a real licence: a body naming no licence at all. The widening
# must leave `unknown` alone rather than turning it into `allow`.
BODY_NAMING_NOTHING = (
    "Terms of use for this package\n"
    "\n"
    "You may use this software and its documentation, and you may\n"
    "redistribute it, provided you keep this notice intact.\n"
    ""
)

# Constructed, not a real licence: a body that *declares* MIT and *mentions* the
# GPL. It classifies allow, and that is the right answer about the package — it
# is MIT-licensed. It would be the wrong answer to "does anything here mention
# copyleft", which is not the question this checker asks. Pinned because the
# distinction is the whole basis of `classify_body`.
MIT_BODY_MENTIONING_GPL = (
    "MIT License\n"
    "\n"
    "Copyright (c) 2026 Example\n"
    "\n"
    "Permission is hereby granted, free of charge, to any person obtaining a\n"
    "copy of this software to deal in the Software without restriction.\n"
    "\n"
    "Note: this package links against a library distributed under the GNU\n"
    "General Public License. That library is not vendored here.\n"
    ""
)

BODY_CASES = [
    ("tiktoken's real 1078-character MIT text", TIKTOKEN_LICENSE_BODY, "allow", "permissive"),
    (
        "the real GPL-2, which names the LGPL in its preamble",
        GPL2_LICENSE_BODY,
        "deny",
        "strong copyleft",
    ),
    (
        "the real GPL-3, which names the AGPL in section 13",
        GPL3_LICENSE_BODY,
        "deny",
        "strong copyleft",
    ),
    (
        "the real LGPL-3 title, which contains the GPL rule's phrase too",
        LGPL3_LICENSE_BODY,
        "review",
        "weak copyleft",
    ),
    (
        "the real Apache-2.0, which says 'commercial' in its liability clause",
        APACHE2_LICENSE_BODY,
        "allow",
        "permissive",
    ),
    (
        "the real AGPL-3 preamble, where Affero must win inside the title",
        AGPL3_LICENSE_BODY,
        "deny",
        "network copyleft",
    ),
    (
        "the real BSD text — known wrong, recorded not endorsed",
        BSD_LICENSE_BODY,
        "deny",
        "not redistributable",
    ),
    (
        "the real MPL-2.0 text — known wrong, recorded not endorsed",
        MPL2_LICENSE_BODY,
        "deny",
        "strong copyleft",
    ),
    ("a body naming no licence at all", BODY_NAMING_NOTHING, "unknown", "unrecognized"),
    ("a body declaring MIT that mentions the GPL", MIT_BODY_MENTIONING_GPL, "allow", "permissive"),
]

for label, body, want_verdict, want_reason in BODY_CASES:
    verdict, reason = classify(body)
    check(f"licenses: body — {label} (verdict)", verdict, want_verdict)
    check(f"licenses: body — {label} (reason)", want_reason in reason, True)

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
total = len(LICENSE_CASES) + 2 * len(BODY_CASES) + 15 + 16
if failures:
    print(f"FAIL: {len(failures)} of {total} checks failed:", file=sys.stderr)
    for line in failures:
        print(f"  {line}", file=sys.stderr)
    sys.exit(1)

print(f"OK: {total} checks passed.")
