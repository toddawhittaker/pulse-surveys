#!/usr/bin/env python3
"""Answer one question about a diff: did it touch anything but inert documentation?

Ticket E0-38. `.github/workflows/ci.yml` had no path filtering, so a pull request
touching only Markdown ran pytest against testcontainers, built both images,
brought up the Compose stack, ran Playwright, ran the eval floors and audited the
supply chain — about fifteen minutes of runner time to establish that no Python
changed, on a shape this epic produced six times.

Usage:
    classify_changed_paths.py <changed path>...

    exit 0  every path is inert; the expensive gates may short-circuit
    exit 1  something outside the inert set changed; run everything

**The polarity is the safety property, not a convention.** A script that is
missing, that crashes, or that meets something it cannot make sense of exits
non-zero, and the pipeline reads non-zero as "run everything". Every way this can
go wrong therefore falls toward the full run. Reversing the two exits would make a
crash indistinguishable from a documentation-only diff and skip every gate on it.

**The set is an allowlist and never a denylist.** A path nobody has classified is
not inert. The difference only shows on paths nobody thought about: "inert unless
it is a `.py`" gets every case in the suite right and silently skips the gates on
a new lockfile, a Compose file, or a prompt.

**A `docs/` prefix is not a safe skip set on its own.** `test_ai_contracts.py`
parses SPEC §7.4's task table and verdict sets out of `docs/SPEC.md` at test time,
so that changing a verdict takes an edit to the spec rather than to a constant
nobody reads. PR #39 edited it, and pytest was the one job with any business
running. So the parsed documents are excepted below, by name.

**Why by name, rather than derived from the suite.** E0-38 offers the stronger
form — read the suite and find out which documents it opens — and it is the wrong
trade here, for one reason. The guard on this script sweeps the suite for exactly
those paths and asserts this script calls each one not-inert. If this script
derived the same set by the same walk, that guard could not fail: it would be
comparing an answer with itself, which is `docs/MISTAKES.md` entry 19. Hand the
derivation to the guard and keep the guarded thing simple, and a new
document-reading module turns that sweep red on the pull request that adds it,
with a message naming the file to except. The cost is one line here, paid by
whoever teaches a module to read a new document, and it is loud rather than
silent.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Directories whose entire contents are inert. `docs/` holds the spec, the ADRs,
# the tickets, the mistakes files and the disputes; `design/` holds the canvases
# and their notes. Nothing in either is imported, executed, packaged or linted.
INERT_DIRECTORIES = ("docs/", "design/")

# Documents something in the suite parses at run time, which are therefore the
# opposite of inert: editing one is exactly when the suite that reads it has to
# run. Repository-relative, and checked before the directories above.
#
# Keep this in step with the suite. The sweep named in the module docstring is
# what says it has fallen behind, and it names the file and the module that reads
# it when it does.
PARSED_DOCUMENTS = frozenset(
    {
        "docs/SPEC.md",
        # Not parsed by a test — declared as a build input. `pyproject.toml` names
        # it as the wheel's readme and `backend/Dockerfile` copies it in
        # `COPY pyproject.toml README.md ./`, so deleting it breaks the image
        # build. Calling it inert meant a README-only pull request did not build
        # the image that packages it, and a deletion surfaced on some later
        # unrelated pull request instead of on the one that caused it. The saving
        # given up is README-only pull requests, which this epic has produced
        # none of; what it buys is that no declared build input sits in the set
        # that switches the build off. E0-38's security review raised it and
        # ADR 0070 records the reversal.
        "README.md",
    }
)


def is_inert(path: str) -> bool:
    """Whether one changed path is documentation nothing depends on.

    Paths are taken as given and never resolved against the filesystem. A diff
    shows a deleted file and a new one exactly as it shows an edited one —
    trimming `docs/mistakes/` is a real change of that shape — so requiring the
    file to exist would send every documentation deletion down the full pipeline.
    """
    # A path with a `..` segment is refused rather than resolved. Nothing in a
    # `git diff --name-only` produces one today, so this is unreachable from the
    # workflow; it is one line, and the alternative is that the first caller who
    # does produce one gets `docs/../backend/app/main.py` classified as inert.
    if ".." in Path(path).parts:
        return False

    if path in PARSED_DOCUMENTS:
        return False
    if path.startswith(INERT_DIRECTORIES):
        return True
    # A Markdown file at the repository root: README.md, CONTRIBUTING.md,
    # CLAUDE.md. At the root only — `backend/app/ai/prompts/validity.v1.md` is
    # Markdown and is not documentation. It is a prompt, versioned in-repo under
    # SPEC §7.4, and editing it changes what every §9.3 eval floor measures,
    # including the threat and self-harm recall floor CLAUDE.md calls a hard gate.
    # A rule written as "a `.md` file is documentation" would skip the eval gate
    # on the one change that most needs it.
    return "/" not in path and path.endswith(".md")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "paths",
        nargs="*",
        help="the paths a diff touched, repository-relative",
    )
    args = parser.parse_args()

    # A path beginning with a dash is refused rather than classified. argparse
    # answers before this function runs, so a caller that forgets `--` never
    # reaches here at all: a repository root file named `-h` prints the usage and
    # exits 0, which is this script's "inert" answer, and switches off every
    # expensive gate with the required check green. `-hx` and `--hel` do the same
    # by short-option clustering and abbreviation. The workflow passes `--`, and
    # this is the second half, because the usage above advertises a general
    # command line and the next caller will not have read that comment.
    dashed = [path for path in args.paths if path.startswith("-")]
    if dashed:
        print(
            f"not inert: {len(dashed)} path(s) begin with a dash, which this script "
            "refuses to classify because argparse would answer first:",
            file=sys.stderr,
        )
        for path in dashed:
            print(f"  {path}", file=sys.stderr)
        return 1

    # An empty list is not a documentation-only change; it is the absence of
    # evidence. The likeliest way to produce one is not an empty commit but the
    # diff failing quietly — a base ref that is not there, a shallow clone with no
    # merge base, a comparison against the wrong SHA — and in each of those
    # "nothing changed" is false. Reading it as inert would turn a broken path
    # computation into a green required check over a pipeline that never ran.
    if not args.paths:
        print(
            "not inert: no changed paths were given. An empty diff is treated as "
            "unknown rather than as documentation, because the usual cause is the "
            "diff computation failing rather than nothing having changed.",
            file=sys.stderr,
        )
        return 1

    outside = [path for path in args.paths if not is_inert(path)]

    if outside:
        print(f"not inert: {len(outside)} of {len(args.paths)} changed path(s) sit outside the")
        print("inert set, so every gate runs:")
        for path in outside:
            why = " (parsed at run time by the suite)" if path in PARSED_DOCUMENTS else ""
            print(f"  {path}{why}")
        return 1

    print(f"inert: all {len(args.paths)} changed path(s) are documentation nothing depends on:")
    for path in args.paths:
        print(f"  {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
