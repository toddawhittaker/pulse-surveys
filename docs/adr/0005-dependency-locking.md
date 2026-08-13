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
`pip install -e . --no-deps`. `make lock` regenerates both files; `make install`
installs them.

The lockfiles are the audited artifact too: `pip-audit` reads them directly
rather than scanning an installed environment, and the license check installs
the runtime closure alone before scanning.

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
- **Dependabot updates get slower to review.** A minor bump rewrites hash blocks
  for every affected package, so the diff is large and mostly noise. Dependabot
  does regenerate hashes for pip-compile output, so it stays automatic.
- **`pip-audit --strict` cannot audit an editable install** — it refuses to skip
  one, even with `--skip-editable`. Auditing the lockfiles sidesteps that
  entirely, and has the better property anyway: what is audited is what is
  pinned, whether or not it has been installed.
- Every container image and every future CI job installs the same way, or the
  guarantee is only as good as the sloppiest install line.
