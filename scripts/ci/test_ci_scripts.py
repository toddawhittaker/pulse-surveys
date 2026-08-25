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


def run_refusing(script: str, *args: str) -> tuple[int, bool]:
    """A checker's exit status, and whether it got there by crashing.

    For the cases whose expected answer is a *refusal*. `== 1` alone does not say
    one happened: an uncaught exception also exits 1, so a checker that throws
    `FileNotFoundError` on a missing directory satisfies "missing dist fails"
    while having no rule about missing directories at all. That is
    `docs/MISTAKES.md` entry 3 — a test passing for a reason unrelated to what it
    asserts — and it is a live risk here, because the case being added is
    precisely the one where the path is not there.

    The wording of the refusal is deliberately not asserted. What is asserted is
    that the script decided.
    """
    # S603: as above — this interpreter and a checker script from this directory.
    completed = subprocess.run(  # noqa: S603
        [sys.executable, str(HERE / script), *args],
        capture_output=True,
        text=True,
    )
    return completed.returncode, "Traceback (most recent call last)" in (
        completed.stdout + completed.stderr
    )


# What a refusal looks like: exit 1, and no traceback in the output. Spelled out
# rather than shared with the `REFUSED` the invariant-assertion section defines
# further down — that one is a different pair about a different checker, and one
# name for two shapes is how they would come to be read as the same thing.
REFUSED_WITHOUT_CRASHING = (1, False)


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

# ---------------------------------------------------------------------------
# classify_changed_paths.py — E0-38
# ---------------------------------------------------------------------------
# **Why this battery is here as well as under `tests/`.** The unit-test copy runs
# in the `test` job, and the `test` job is one of the five this classifier can
# switch off. So if the classification is wrongly permissive about some family of
# paths, a pull request touching only that family short-circuits `test` and the
# assertions that would have caught it do not run — the classifier's mistake
# hiding the evidence of itself. That is the exact hazard this file's header
# describes and the reason `ci-selftest` exists, and E0-38 keeps that job
# unconditional for it. These cases run there.
#
# It is deliberate duplication across the test wall, not an oversight: the module
# under `tests/` is written from the ticket, this one from the contract, and the
# point of the copy is that it runs when the other one cannot.
#
# Exit 0 is inert (the expensive gates may short-circuit) and exit 1 is not
# inert. Both directions are exercised, so a classifier that answers the same
# thing to everything fails whichever answer it picked.
CLASSIFIER_CASES = [
    # Inert: the three families E0-38's scope names.
    ("a ticket", ["docs/tickets/e0/README.md"], 0),
    ("the mistakes file", ["docs/MISTAKES.md"], 0),
    ("an architecture decision record", ["docs/adr/0002-ci-gates-ship-tolerant.md"], 0),
    # A diff shows a deleted file and a new one exactly as it shows an edited
    # one, so the classifier must never require the path to exist.
    ("a document that is not in the tree", ["docs/adr/0071-invented.md"], 0),
    ("a design file whose name has a space in it", ["design/Usage Rules.md"], 0),
    ("a root Markdown file", ["CONTRIBUTING.md"], 0),
    (
        "several inert families at once",
        ["CLAUDE.md", "docs/MISTAKES.md", "design/tokens.css"],
        0,
    ),
    # `README.md` is a root Markdown file and is *not* inert: `pyproject.toml`
    # declares it as the wheel's readme and `backend/Dockerfile` copies it, so
    # it is a declared build input. E0-38's security review asked whether a
    # build input belongs in the set that switches the build off; ADR 0070
    # records the reversal.
    ("the readme, which is a declared build input", ["README.md"], 1),
    # Not inert. The spec is the one the naive version gets wrong: it is parsed
    # at run time by the contract suite, so editing it is exactly when that suite
    # has to run. PR #39 is the incident.
    ("the spec, which the contract suite parses at run time", ["docs/SPEC.md"], 1),
    # A `.py` file is never inert however documentary the edit. The classifier is
    # given paths and never contents, which is the point: "did any `.py` change"
    # is right where "did this feel like documentation" is not.
    ("a Python file", ["backend/app/services/authz.py"], 1),
    # A prompt is Markdown and is not documentation. It is versioned in-repo
    # under SPEC §7.4 and editing it changes what every §9.3 eval floor measures,
    # so a rule written as "a `.md` file is documentation" skips the eval gate on
    # the one change that most needs it.
    ("a prompt, which is Markdown", ["backend/app/ai/prompts/validity.v1.md"], 1),
    ("the workflow that decides which gates run", [".github/workflows/ci.yml"], 1),
    ("the project metadata", ["pyproject.toml"], 1),
    ("a hash-pinned lockfile", ["requirements.txt"], 1),
    ("the Compose file the build gate brings up", ["docker-compose.yml"], 1),
    # The allowlist test: a path nobody has classified runs everything. This is
    # what tells an allowlist from a denylist, and every other case here is
    # satisfied by either.
    ("a path of a kind nobody has met", ["ops/whatever/thing.unheard-of"], 1),
    # One path outside the set is the whole answer, whatever it sits beside and
    # in whichever order the paths arrive.
    ("a Python file after inert documentation", ["docs/MISTAKES.md", "backend/app/main.py"], 1),
    ("a Python file before inert documentation", ["backend/app/main.py", "docs/MISTAKES.md"], 1),
    # An empty diff is the absence of evidence, and its usual cause is the diff
    # computation failing rather than nothing having changed. Reading it as inert
    # would turn a broken path computation into a green required check over a
    # pipeline that never ran.
    ("an empty diff", [], 1),
    # Leading-dash paths. Passed after `--`, as the workflow passes them, these
    # reach the script and it refuses them. Without `--` argparse answers first
    # and `-h` exits 0 — the "inert" answer — which switched off five jobs with
    # the required check green. E0-38's security review found it; the near
    # misses are the reason nothing else did, because `-q` exits 2 and lands in
    # the workflow's "neither answer" branch, which fails safe.
    ("a root file named -h, after --", ["--", "-h"], 1),
    ("a short-option cluster, after --", ["--", "-hx"], 1),
    ("an argparse abbreviation, after --", ["--", "--hel"], 1),
    ("a leading-dash path beside a real one", ["--", "-h", "backend/app/main.py"], 1),
    ("a dash path that is not an option at all", ["--", "-q"], 1),
    # The near misses. After `--`, `-h` is a positional path and the inert set
    # rejects it anyway; a dash-named *root Markdown file* is an inert family,
    # so these are the cases the script's own refusal is actually for.
    ("a dash-named root Markdown file", ["--", "-h.md"], 1),
    ("a dash-named root Markdown file spelled long", ["--", "--help.md"], 1),
    # A `..` segment is refused rather than resolved. Unreachable from
    # `git diff --name-only` today; one line, and the alternative is that the
    # first caller who produces one gets a code path classified as inert.
    ("a path escaping the inert directory", ["docs/../backend/app/main.py"], 1),
]

for label, paths, want_exit in CLASSIFIER_CASES:
    check(f"changed paths: {label}", run("classify_changed_paths.py", *paths), want_exit)

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
    # **Two of these cases changed answer in E1-04, and the change is the ticket.**
    # A missing `frontend/dist` and a dist holding no JavaScript were notes that
    # exited 0, which was right while the gate was tolerant: the build had nothing
    # to produce, so measuring nothing was the honest outcome and ADR 0002's notice
    # said so. E1-04 makes the production build enforcing, so this script now runs
    # only ever *after* a build that was required to succeed — and in that world
    # "there is no dist" and "the dist has no JavaScript" are not notes about an
    # absent frontend, they are the two ways a build can appear to succeed and
    # produce nothing. Exiting 0 on either is the gate reporting green over an
    # empty measurement, which ADR 0083 rejected in advance for this exact script:
    # "two gates would report green having measured an empty tree… a gate turned on
    # and made meaningless".
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

    # A dist that exists, was produced by something, and carries no JavaScript at
    # all — the shape a build leaves when its entry point moved, when it wrote to
    # another directory, or when a plugin swallowed the bundle. It is the case that
    # tells "the budget was measured and met" apart from "nothing was measured",
    # and the two are the same exit code without it.
    empty_dist = d / "dist-without-javascript"
    (empty_dist / "assets").mkdir(parents=True)
    (empty_dist / "index.html").write_text("<!doctype html><html></html>")
    (empty_dist / "assets" / "index-abc.css").write_text("body{margin:0}")
    check(
        "bundle: a dist with no JavaScript is refused",
        run_refusing("check_bundle_size.py", str(empty_dist), "--budget", str(budget)),
        REFUSED_WITHOUT_CRASHING,
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
        "bundle: a missing dist is refused",
        run_refusing("check_bundle_size.py", str(d / "no-dist"), "--budget", str(budget)),
        REFUSED_WITHOUT_CRASHING,
    )

    # Sanity: the oversized fixture really is oversized after gzip, so the
    # assertion above is testing the budget and not a quirk of compression.
    if len(gzip.compress(big, compresslevel=9)) <= 4096:
        failures.append("bundle: fixture compressed below the budget; test is vacuous")

    # -----------------------------------------------------------------------
    # ci/bundle-budget.json — the numbers the gate reads
    # -----------------------------------------------------------------------
    # E1-04's scope: "The bundle budget's number is set here and recorded where the
    # gate reads it, with one sentence on how it was chosen." The numbers
    # themselves are not asserted — they are the implementer's measurement against
    # the first real production build, and a test that pinned them would be a
    # second copy of the budget with no way to move (`docs/MISTAKES.md` entry 19).
    # What is asserted is that the file the gate reads still declares both limits,
    # and that what it says about where they came from is no longer the sentence it
    # says today.
    BUDGET_ENTRY_KEY = "max_entry_js_gzip_bytes"
    BUDGET_INITIAL_KEY = "max_initial_gzip_bytes"

    # Copied whole out of `ci/bundle-budget.json`, the line it begins on included —
    # `docs/MISTAKES.md` entry 3, whose rule is that a canary retyped from where you
    # think a sentence starts is the thing the canary exists to disprove. The
    # sentence spans two array elements, so the needle is the part of it inside the
    # first: a search for the whole sentence would match nothing and report a
    # re-baselined file whatever the file said.
    BUDGET_COMMENT_AS_IT_STOOD = (
        '    "Starting values are an estimate, not a measurement: the frontend does not",\n'
        '    "exist yet. Expected occupants are React 19, TanStack Router and Query, and",\n'
    )
    BUDGET_PLACEHOLDER = "Starting values are an estimate, not a measurement"

    check(
        "bundle: the estimate search can see the sentence it refuses",
        BUDGET_PLACEHOLDER in BUDGET_COMMENT_AS_IT_STOOD,
        True,
    )

    committed_budget_path = HERE.parent.parent / "ci" / "bundle-budget.json"
    committed_budget_text = (
        committed_budget_path.read_text() if committed_budget_path.is_file() else ""
    )
    committed_budget = json.loads(committed_budget_text) if committed_budget_text else {}

    for key in (BUDGET_ENTRY_KEY, BUDGET_INITIAL_KEY):
        value = committed_budget.get(key)
        check(
            f"bundle: the committed budget declares a positive {key}",
            isinstance(value, int) and not isinstance(value, bool) and value > 0,
            True,
        )

    # Any key whose value is prose. The spelling is not pinned — the file uses
    # `_comment` today and JSON has no comments, so some key has to carry the
    # rationale and which one is not a decision this test makes.
    rationale = [
        value
        for key, value in committed_budget.items()
        if key not in (BUDGET_ENTRY_KEY, BUDGET_INITIAL_KEY)
        and any(str(line).strip() for line in (value if isinstance(value, list) else [value]))
    ]
    check(
        "bundle: the committed budget records how its numbers were chosen",
        bool(rationale),
        True,
    )

    # The forbidden state rather than the permitted one (`docs/MISTAKES.md` entry
    # 2): what "recorded with one sentence on how it was chosen" rules out is the
    # sentence that is there now, which says in as many words that the numbers were
    # never measured because the frontend did not exist. E1-04 is the ticket where
    # it does.
    check(
        "bundle: the committed budget no longer calls its numbers an estimate",
        BUDGET_PLACEHOLDER in committed_budget_text,
        False,
    )

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
# 4 licence cases, 8 invariant-report cases, 9 bundle cases (E1-04 took the bundle
# section from 3 to 9: two exit codes changed answer with the gate flip, and the
# committed budget file gained four checks of its own), 16 invariant-assertion
# cases.
total = len(LICENSE_CASES) + 2 * len(BODY_CASES) + len(CLASSIFIER_CASES) + 21 + 16
if failures:
    print(f"FAIL: {len(failures)} of {total} checks failed:", file=sys.stderr)
    for line in failures:
        print(f"  {line}", file=sys.stderr)
    sys.exit(1)

print(f"OK: {total} checks passed.")
