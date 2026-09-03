# 0039 — The two `app` packages are typechecked in two mypy runs

**Status:** Accepted
**Date:** 2026-08-16
**Tickets:** E0-14

## Context

[SPEC §13](../SPEC.md) puts a package called `app` under `backend/` and a second
package called `app` under `mock-lms/`. Both are Python source that ships in an
image, and `CLAUDE.md` asks for fully typed modern Python.

`pyproject.toml` configures mypy with `files = ["backend/app"]`, so E0-14's new
code would be linted by ruff and typechecked by nothing.

Extending `files` does not work, and this was measured rather than reasoned
about:

```
$ mypy backend/app mock-lms/app
mock-lms/app/__init__.py: error: Duplicate module named "app" (also at "backend/app/__init__.py")
Found 1 error in 1 file (errors prevented further checking)
```

"Errors prevented further checking" is the part that matters: one run over the
two checks *neither*.

## Decision

mypy runs twice. `mypy` with the project configuration covers `backend/app`, and
`mypy mock-lms/app` covers the mock. Both `make typecheck` and the `fast-gate`
job in `.github/workflows/ci.yml` run the pair, in that order.

The second run inherits the project's mypy configuration — the same Python
version, the same warnings — and takes its files from the command line, which
overrides `files`. The strict profile in `pyproject.toml` is scoped to
`app.services.*`, `app.ai.contracts`, and — since the quality-review cleanups,
2026-08-24 — `app.api.*` and `app.lti.*`; none of those module names exist in
either mock (neither ships an `api` or `lti` subpackage), so the mock is
checked at the default strictness. (Amended 2026-08-24; the original named only
the first two, which was true when written.)

## Alternatives rejected

**Rename one of the packages.** `mock_lms.app`, or `platform_app`. It would make
one run possible, and it contradicts SPEC §13, which names both directories and
both `app/` packages. A layout change to satisfy a type checker is the wrong way
round.

**`--explicit-package-bases` with `MYPYPATH`.** Makes the two resolvable as
distinct modules in one run, at the cost of a flag combination nobody reading the
Makefile would understand and a resolution order that depends on `MYPYPATH`
ordering — the same class of ambiguity `tests/conftest.py` installs a scoped
finder to avoid at import time.

**Leave `mock-lms/` unchecked and say so.** Honest, and it leaves a service that
signs tokens outside the gate that every other Python file in the repository
passes. The cost of closing it is one line in two files.

**A separate mypy configuration file for the mock.** A second configuration to
keep in step with the first, for a difference that is one path argument.

## Consequences

**Two invocations have to stay in step in two places** — the Makefile and the
workflow — which is the same obligation E0-03 already carries for the health
gate, and `CLAUDE.md` already says which wins when they disagree: the workflow.

**They share one `.mypy_cache`.** Running the first two alternately four times was checked
for cache confusion between two module trees with the same module names; the
results were stable and correct in both directions. If that ever changes, the fix
is `--cache-dir` on the second run, not one run.

**A third `app` package needed a third run, and E0-16 added it.** `mock-idp/`
is that package, and `mypy mock-idp/app` follows the other two in
`.github/workflows/ci.yml` and in `make typecheck`. The rule generalises as
written: an `n`th package called `app` is an `n`th invocation, in both files, in
the same order.

**A fourth arrived with E2-07**, and the rule held without amendment:
`mypy mock-ai/app` follows the other three in the same two files. The count in
this record's title is therefore two behind and is left alone, because renumbering
and retitling records is what this directory's index forbids — the decision is the
invocation-per-package rule, not the number two.
