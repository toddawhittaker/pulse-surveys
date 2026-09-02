# Entry 38. An option parser answered before the guard did, and its answer was the permissive one

**Caught: 1**

*Part of [docs/MISTAKES.md](../MISTAKES.md). The number is this entry's name — citations point at it, so it never changes.*

*2 instances recorded, newest first.*

*(**2026-09-02, E2-12 (`e2/eval-floors`), caught before it landed.** The same
script grows a second classification, deciding whether SPEC §9.3's eval floors
run — the gate `CLAUDE.md` calls a hard one. Acting on this entry, the test
author asked the leading-dash question of the *new* question rather than
assuming E0-38's fix covered it, and asked it in the shape this entry's closing
paragraph prescribes: a bare `-h`, a `-h` sitting beside a prompt edit, a path
spelled like the new option's own name, and the near miss that separates the fix
from doing nothing — an ordinary path containing dashes, which must stay
classified. The implementer then routed both guards through the single
leading-dash refusal already in the script and the single `--` already in the
workflow, rather than writing a second copy for the second question, and
executed the whole table against the built script. Counted as a catch: without
the case, the new code path had no reason to inherit either half, and a
dash-named file beside a prompt edit would have exited 0 — the answer that lets
the floors stay off — with the required check green.)*

*(E0-38, found by the security review after the build was green, two live
scratch-branch pushes had confirmed the behaviour, and a fifteen-row mutation
table had come back clean.

`scripts/ci/classify_changed_paths.py` decides whether a diff is inert
documentation. Exit 0 means inert and switches off pytest, the §4.1 invariant
suite, both image builds, Playwright, the evals and the supply-chain audit; exit
1 means run everything. The script is written to fail toward exit 1 — a path
nobody has classified, a crash, an empty diff, a missing base commit all run the
full pipeline — and the workflow step around it reads the exit status as three
cases and warns loudly on anything that is neither answer. All of that reasoning
is correct and none of it runs.

The workflow invoked it as `python3 classify_changed_paths.py "${changed[@]}"`,
with no `--` separator, and the path list comes from `git diff --name-only`. A
repository root file named `-h` therefore arrives as an argument, argparse
recognises it, prints the usage and exits **0** — the inert answer — before
`main()` executes a single line. The class is wider than the obvious one: `-hx`
is a short-option cluster containing `-h`, and `--hel` is an unambiguous
abbreviation of `--help`, so both do the same.

**Every near miss fails safe, which is why nothing caught it.** `-q` is not a
valid option, so argparse exits 2, which lands in the step's "neither answer"
branch and runs everything. Only the options argparse actually recognises are
dangerous. A mutation battery, a self-test battery of a hundred checks, and two
real pushes to GitHub all exercised the script through its intended door and
none of them knocked on this one.

The fix is two halves and both are deliberate. The workflow passes `--`, so
argparse never sees a path. The script also refuses any argument beginning with
a dash, because its usage message advertises a general command line and the next
caller will not have read the comment. Neither half is redundant: with `--`
alone, a root file named `-h.md` is a Markdown file at the repository root, which
is an inert family, so it classifies inert. That near miss is now a case in both
batteries — without it the script's own refusal looks like decoration and the
next person deletes it.)*

## The rule

**When a guard takes untrusted names as command-line arguments, the argument
parser is part of the guard.** Pass `--` before any list that came from a diff, a
glob, a directory listing or a user, and have the script refuse leading-dash
arguments as well.

The general shape is worth more than the specific fix: **a decision made before
your logic runs is still your decision.** An option parser, a shell's own word
splitting, a redirect, a wrapper script's `set -e` — each answers first, and each
can answer the permissive way. When a control is written to fail closed, check
what happens *upstream* of the first line you wrote, not only along the paths you
wrote.

And when you test it, include the near miss that distinguishes the fix from doing
nothing. Here that is `-h.md` rather than `-h`: the bare case passes with the fix
removed, so a battery holding only bare cases would have said the fix was
unnecessary.
