#!/usr/bin/env python3
"""Answer one of two questions about a diff, and both decide whether a gate runs.

Ticket E0-38 asked the first: **did it touch anything but inert documentation?**
`.github/workflows/ci.yml` had no path filtering, so a pull request touching only
Markdown ran pytest against testcontainers, built both images, brought up the
Compose stack, ran Playwright, ran the eval floors and audited the supply chain —
about fifteen minutes of runner time to establish that no Python changed, on a
shape this epic produced six times.

Ticket E2-12 asks the second: **did it touch the AI surface?** SPEC §9.3's eval
floors are the one gate in this pipeline that calls a paid provider, about a
hundred requests a run, and §9.3 scopes them to "prompt or model changes". So the
live eval steps run on a diff that touches `backend/app/ai/`, `tests/evals/`, or
one of the three files that say which model is asked and how — the settings
module, the documented configuration surface, and the workflow that carries the
eval job's own wiring — and on nothing else.

Usage:
    classify_changed_paths.py [--classification inert|ai-surface] -- <changed path>...

    --classification inert (the default, and how E0-38's caller invokes it)
      exit 0  every path is inert; the expensive gates may short-circuit
      exit 1  something outside the inert set changed; run everything

    --classification ai-surface
      exit 0  no changed path is an AI surface; the eval steps may stay off
      exit 1  at least one is; the eval steps must run

**The polarity is the safety property, not a convention, and it is one polarity
for both questions.** Exit 0 always means "the gates this decides may
short-circuit" and exit 1 always means "run them". A script that is missing, that
crashes, or that meets something it cannot make sense of exits non-zero, so every
way this can go wrong falls toward running the gate. Reversing either pair would
make a crash indistinguishable from a diff nobody needs to test, and a second
question whose 0 meant the opposite would be a trap nobody could read off the
shell.

**Adding the second question must not cost the first answer**, which is why
`--classification` has a default rather than being required: the `changed` job's
existing call passes no flag at all, and it switches off pytest, the §4.1
invariant suite, both image builds, Playwright and the audit. A new option that
made that call an error would have broken every pull request in the repository
while satisfying every case written for the new question (`docs/MISTAKES.md`
entry 22).

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
        # The second file to make that move, on the same two properties, and it
        # holds both more strongly than the readme does. E1-04 landed the frontend
        # and made this a build input twice over:
        #
        #   * `frontend/src/styles.css` opens with
        #     `@import '../../design/tokens.css'`, so the palette, the type scale,
        #     the spacing ramp, the radii, the focus ring and the reduced-motion
        #     kill switch are compiled into `frontend/dist/assets/*.css` and served
        #     to every person who lands on a view. The readme is *packaged* and
        #     never rendered; this file is rendered to everybody.
        #   * `backend/Dockerfile`'s frontend stage carries
        #     `COPY design/tokens.css ./design/tokens.css`, so deleting or
        #     renaming it breaks the image build — the same sentence as the readme
        #     entry above.
        #
        # Called inert, a palette edit built no bundle, measured no budget and
        # built no image, all reporting success, and a deletion surfaced on some
        # later unrelated pull request instead of on the one that caused it.
        # SPEC §7.6's "single source" forecloses the change that would have kept it
        # inert — a copy of the token definitions under `frontend/src/`.
        #
        # The coverage given up is tokens-only pull requests short-circuiting,
        # which is a saving this repository has never taken: `git log --follow`
        # over this file reports one commit in the whole history, the initial
        # prototype export. What it buys is the same thing the readme entry buys —
        # no declared build input sitting in the set that switches the build off.
        #
        # Ruled in `docs/disputes/E1-04-01.md`; ADR 0070 is the precedent, applied
        # rather than extended. **Only this path moves.** The rest of `design/` is
        # genuinely inert — nothing imports a `.dc.html` prototype canvas or a
        # usage note, and no `COPY` names one — and the `design/` entry in
        # `INERT_DIRECTORIES` above is unchanged.
        "design/tokens.css",
    }
)


# Directories whose entire contents are the AI surface. SPEC §9.3's gate is
# "prompt or model changes", and everything a model call passes through lives
# under one of these two: the gateway, the task functions, the typed contracts and
# the versioned prompt files under `backend/app/ai/`, and the runner, the eval
# sets and the floor declarations under `tests/evals/`.
#
# **"Under", and not "starts with".** `backend/app/ai_helpers.py` and
# `tests/evals_archive/` are not in either tree, and a prefix comparison says they
# are — which fires a paid gate on files that have nothing to do with a model. The
# trailing slash is what makes the difference, and it is the whole of the rule.
AI_SURFACE_DIRECTORIES = ("backend/app/ai/", "tests/evals/")

# Files that are the AI surface without being under either directory, because they
# carry the model identifier. E2-12's scope argues the trade: "Over-firing on an
# unrelated config edit costs one eval run; under-firing on a model bump is §9.3's
# gate not running, which is the worse trade by the ADR 0002 incident record."
#
# **"Equals", and not "starts with", and that is a second rule rather than the
# same one.** `.env.example.local` and `backend/app/config.py.bak` are files
# somebody will plausibly create, and a single prefix comparison collapses the two
# rules into one and fires on both.
#
# **The workflow joined this set in E2-12's security review**, and the argument is
# the one the two entries above already carry. `.github/workflows/ci.yml` holds
# the eval job's own wiring — which endpoint the run reaches, which model it asks
# for, the secret binding, the step conditions — and it was in neither this set
# nor the directory set. So the single file that decides what CI measures could
# not fire the gate that measures it, and a model pin edited there would have
# shipped without one eval call: exactly the change SPEC §9.3's gate is named
# after. The cost is that an unrelated workflow edit now pays for an eval run,
# which is the trade the ticket settles in as many words — over-firing costs one
# run, under-firing is the gate not running, and the second is worse by the ADR
# 0002 incident record.
AI_SURFACE_FILES = frozenset({"backend/app/config.py", ".env.example", ".github/workflows/ci.yml"})


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


def is_an_ai_surface(path: str) -> bool:
    """Whether one changed path is something SPEC §9.3's eval floors measure.

    Two rules rather than one, because E2-12's scope states two: *under* the two
    directories, and *equal to* the two files. See the constants above for what a
    single prefix comparison would do to each.

    Paths are taken as given and never resolved against the filesystem, for the
    reason `is_inert` gives: a diff shows a deleted file exactly as it shows an
    edited one, and deleting a prompt is a change the floors have every reason to
    run on.
    """
    # Refused rather than resolved, on the same terms as `is_inert` and in the
    # safe direction for this question too: an unclassifiable path is not the AI
    # surface's business, and the caller below is what turns "cannot classify"
    # into "run the gate".
    if ".." in Path(path).parts:
        return False

    return path in AI_SURFACE_FILES or path.startswith(AI_SURFACE_DIRECTORIES)


INERT = "inert"
AI_SURFACE = "ai-surface"


def report_inert(paths: list[str]) -> int:
    """E0-38's question. Exit 0 when every path is documentation nothing depends on."""
    outside = [path for path in paths if not is_inert(path)]

    if outside:
        print(f"not inert: {len(outside)} of {len(paths)} changed path(s) sit outside the")
        print("inert set, so every gate runs:")
        for path in outside:
            why = " (parsed at run time by the suite)" if path in PARSED_DOCUMENTS else ""
            print(f"  {path}{why}")
        return 1

    print(f"inert: all {len(paths)} changed path(s) are documentation nothing depends on:")
    for path in paths:
        print(f"  {path}")
    return 0


def report_ai_surface(paths: list[str]) -> int:
    """E2-12's question. Exit 0 when no changed path is one SPEC §9.3 measures."""
    touched = [path for path in paths if is_an_ai_surface(path)]

    if touched:
        print(f"ai surface: {len(touched)} of {len(paths)} changed path(s) are the AI surface,")
        print("so the eval floors run:")
        for path in touched:
            print(f"  {path}")
        return 1

    print(f"no ai surface: none of the {len(paths)} changed path(s) is under")
    print(f"{list(AI_SURFACE_DIRECTORIES)} or is one of {sorted(AI_SURFACE_FILES)}:")
    for path in paths:
        print(f"  {path}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    # **Defaulted rather than required**, and that is the half a reviewer's eye
    # slides over. E0-38's caller in `.github/workflows/ci.yml` invokes this
    # script with no flag at all, so a required option here would turn the
    # inert classification into an argparse error — exit 2, which the workflow
    # reads as "run everything" — on every pull request in the repository, while
    # every case written for the new question passed (`docs/MISTAKES.md`
    # entry 22).
    parser.add_argument(
        "--classification",
        choices=(INERT, AI_SURFACE),
        default=INERT,
        help="which question to answer about the diff (default: %(default)s)",
    )
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
            f"{args.classification}: cannot answer — {len(dashed)} path(s) begin with a dash, "
            "which this script refuses to classify because argparse would answer first. "
            "The gates this question decides run:",
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
            f"{args.classification}: cannot answer — no changed paths were given. An empty "
            "diff is treated as unknown rather than as nothing, because the usual cause is "
            "the diff computation failing rather than nothing having changed, and the change "
            "it failed to see may be the model bump. The gates this question decides run.",
            file=sys.stderr,
        )
        return 1

    if args.classification == AI_SURFACE:
        return report_ai_surface(args.paths)
    return report_inert(args.paths)


if __name__ == "__main__":
    sys.exit(main())
