# Entry 25. Two lockfiles resolved the same package to two versions

**Caught: 0**

*Part of [docs/MISTAKES.md](../MISTAKES.md). The number is this entry's name — citations point at it, so it never changes.*


**What happened.** E0-13 added one dependency. `make lock` compiles
`requirements.txt` and `requirements-dev.txt` from `pyproject.toml` in two
separate runs, and the new library brought `requests` — and under it
`charset-normalizer` — into both closures for the first time. The runtime run
pinned `charset-normalizer==3.5.1` and the dev run pinned `3.5.0`, from the same
index, minutes apart, with nothing in either file constraining it and neither
version yanked or restricted. Re-running the dev compile reproduced `3.5.0`, so it
was not a transient.

Nothing that reads one file at a time noticed. `pytest` passed on 654 tests,
`ruff`, `mypy` and the checker self-test were clean, and `pip install
--require-hashes -r requirements-dev.txt` installed happily. **`make audit` is the
only thing in the build that reads both files at once**, and it failed with
`ResolutionImpossible` — a message naming neither the package nor the lockfile,
in a ticket whose change had nothing to do with either.

**Root cause.** Two independent resolutions of overlapping requirement sets. The
dev lock is not compiled against the runtime lock as a constraint, so a package
that both closures pull in transitively is resolved twice, and pip-compile does
not promise the same answer to two different questions.

**Consequence.** A red supply-chain gate whose message points nowhere near the
cause. It was found by running `pip-audit` locally with the same two arguments the
Makefile passes, before opening a pull request; had that not been run, CI would
have reported it against a diff whose only dependency line was for a different
package entirely.

**Rule.** **After `make lock`, check that the two lockfiles agree on every package
they share.** One command, and it costs nothing:

```sh
diff <(grep -oE '^[A-Za-z0-9._-]+==\S+' requirements.txt | sort) \
     <(grep -oE '^[A-Za-z0-9._-]+==\S+' requirements-dev.txt | sort) | grep '^<'
```

Anything it prints that is not simply absent from the dev file is a version skew,
and `--upgrade-package <name>` on the dev compile is the immediate repair. The
durable fix is to compile the dev lock with the runtime lock as a constraint file,
which is a change to `make lock`'s recipe — proposed in E0-13's pull request
rather than made inside it, because the recipe has to keep matching what CI does.

**And run `make audit`'s two arguments together before pushing**, rather than
`pip-audit -r requirements.txt` alone. A gate that reads two files is the only one
that can see a disagreement between them, and reading one file at a time is how
this survived a full green suite.
