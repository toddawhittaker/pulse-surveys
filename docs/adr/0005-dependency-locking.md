# 0005 — Python dependencies are locked with pip-compile, hashes and all

**Status:** Accepted
**Date:** 2026-08-12
**Tickets:** E0-01

## Context

E0-01 declares the backend's dependencies and requires a lockfile committed.
`CLAUDE.md` says to pin versions and commit lockfiles; it does not say with
what. [SPEC §7.1](../SPEC.md) names the libraries and
[§10](../SPEC.md) requires that everything shipped is compatible with MIT
distribution, but neither says how the transitive closure is fixed. So the spec
is silent, and the mechanism is contestable — pip-tools, uv, Poetry, and
"pinned direct dependencies only" all have live advocates.

Two existing pieces of the repository constrain the answer. The CI pipeline
installs with plain `pip` and audits with `pip-audit` and `pip-licenses`
(`.github/workflows/ci.yml`). Dependabot is configured for the `pip` ecosystem
at the repository root (`.github/dependabot.yml`), and it can only propose
upgrades to a lockfile format it can read.

## Decision

Direct dependencies are pinned exactly (`==`) in the `[project]` table of
`pyproject.toml`. The full transitive closure is compiled from there by
`pip-compile` (pip-tools) into two committed files at the repository root:

- `requirements.txt` — the runtime closure. This is what deploys.
- `requirements-dev.txt` — the same, plus the test dependencies.

Both are generated with `--generate-hashes`, so every artifact is fixed by
digest, and every CI job that needs the backend installs with
`pip install --require-hashes -r requirements-dev.txt` followed by
`pip install -e . --no-deps --no-build-isolation`. `make lock` regenerates both
files; `make install` installs them.

The PEP 517 build backend is part of "every artifact", and it is the one piece
`--require-hashes` cannot reach on its own. `pip install -e .` normally builds
in an isolated environment into which pip fetches whatever `[build-system]`
`requires` resolves to, straight from the index and with no digest to check —
and then runs that code. So three things move together:

- `[build-system] requires` pins setuptools exactly, like every other
  dependency, rather than as the floating `>=` range a build backend usually
  gets.
- setuptools is listed in the `dev` extra, which is not where a build
  requirement belongs semantically but is what makes `pip-compile` lock it with
  a hash. It stays out of `requirements.txt`, because nothing ships it.
- Every install site passes `--no-build-isolation`, so the build uses the
  hash-verified copy already installed rather than fetching its own.

`make lock` passes `--allow-unsafe` for the same reason. The flag is named
backwards: it pins the packages pip-tools otherwise leaves floating because pip
itself depends on them. Pinning them is the stricter behaviour, and pip-tools'
own documentation says it will become the default.

The lockfiles are the audited artifact too: `pip-audit` reads them directly
rather than scanning an installed environment. The license check needs
installed distributions to read, so it installs `requirements.txt` — the
runtime lock, not the dev one — into the supply-chain job and scans what is
there. `pip-audit` and `pip-licenses` are installed in that same job, so the
scan covers them and their dependencies as well as the runtime closure. That
is a superset of what §10 governs, and the consequences below say why it is
left that way.

## Alternatives rejected

**uv (`uv lock` / `uv.lock`).** Faster, and the resolver is better. Rejected
because `uv.lock` is not a format `pip`, `pip-audit`, or `pip-licenses` reads,
so every one of those would need an export step or a second tool in CI, and
`uv` itself would become an unpinned bootstrap dependency of every job. The
lock format would also stop being the thing CI installs, which is the property
that keeps a lockfile honest. Worth revisiting when the container images land
(E0-02), where uv's install speed is worth more than it is here.

**Poetry.** Rejected because it wants to own `pyproject.toml` and the build
backend, and the tool configuration already living there — ruff, mypy, pytest,
coverage — is the more valuable resident. It would also put a second dependency
declaration syntax in front of every contributor for no gain over pip-compile.

**Pinned direct dependencies only, no lockfile.** Rejected because it locks the
half of the tree that gets reviewed and leaves the half that does not: a
transitive dependency can change under a `==`-pinned parent between one CI run
and the next, which is exactly the class of supply-chain surprise the audit and
license gates exist to catch. It also contradicts `CLAUDE.md` directly.

**pip-compile without `--generate-hashes`.** Rejected because a version pin
without a digest still trusts whatever the index serves under that version.
Hashes cost one flag and a slower regeneration; they are the part of a lockfile
that resists a compromised or substituted artifact.

**Leaving the build backend on a floating range and building under isolation.**
This is what the first version of this decision did, and it was wrong for the
reason directly above: the range is a version constraint with no digest behind
it, and the artifact it selects is not merely installed but *executed*, in the
runner, with the checkout present. Closing it costs one pin, one lock entry, and
one flag at each install site. That is cheap enough that "an ambient Python
condition everyone lives with" is not a good enough answer when the surrounding
claim is that every artifact is fixed by digest.

**A single combined lockfile.** Rejected because the license gate must scan
what ships and nothing else. §10 is about the distributed closure, and a lock
that cannot separate `pytest` from `fastapi` cannot answer that question.

## Consequences

- **Editing `pyproject.toml` dependencies without running `make lock` breaks
  CI**, since jobs install from the lockfiles and not from `pyproject.toml`.
  That is the intended failure: it is loud, immediate, and fixed by one command.
- **Nothing yet proves the lockfiles agree with `pyproject.toml`.** A stale lock
  that still resolves will install successfully. Regenerating in CI and
  diffing would close that gap, at the cost of a network resolution on every
  run; it is not worth it while the dependency set is this small, and it is the
  first thing to add if drift ever bites.
- **The license scan reads more than we distribute.** `pip-licenses` reports
  every distribution installed in the job, which includes `pip-audit`,
  `pip-licenses`, and their dependencies. Deliberately not narrowed: separating
  them means a second virtual environment for one scan, the extra packages are
  permissively licensed and cost nothing today, and a strict gate that
  occasionally flags a build tool is a better failure than a lenient one that
  misses a shipped dependency. If a tool's dependency ever does trip it, the
  fix is that second environment, and the reason will be obvious in the report.
- **Dependabot updates get slower to review.** A minor bump rewrites hash blocks
  for every affected package, so the diff is large and mostly noise. Dependabot
  does regenerate hashes for pip-compile output, so it stays automatic.
- **`pip-audit --strict` cannot audit an editable install** — it refuses to skip
  one, even with `--skip-editable`. Auditing the lockfiles sidesteps that
  entirely, and has the better property anyway: what is audited is what is
  pinned, whether or not it has been installed.
- **`--no-build-isolation` means the build environment is the runtime
  environment.** A future build requirement — a Cython or Rust toolchain for a
  compiled dependency — has to be installed before the build rather than
  declared and forgotten, and the failure when it is not will read as a missing
  import rather than as a missing build requirement. The compensation is that
  `[build-system] requires` and the `dev` extra must agree; pip checks the
  requirement is satisfied and fails the install when they drift, so this is
  loud rather than silent.
- **Two places now name the setuptools version**, `[build-system]` and the `dev`
  extra, and a Dependabot bump has to move both. Not deduplicated because
  `[build-system]` is read by the build frontend before anything else in the
  file exists, so it cannot reference a dependency group.
- Every container image and every future CI job installs the same way, or the
  guarantee is only as good as the sloppiest install line. `--no-build-isolation`
  is part of "the same way": one install line without it puts an unverified
  build backend back in the pipeline.
