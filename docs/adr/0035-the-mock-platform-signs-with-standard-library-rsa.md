# 0035 — The mock platform signs with standard-library RSA

**Status:** Accepted
**Date:** 2026-08-16
**Tickets:** E0-14

## Context

E0-14 builds the platform side of an LTI 1.3 launch: an issuer key generated per
run, a JWKS endpoint, and a signed `id_token`. That needs two operations —
generate an RSA key pair, and produce an RS256 signature.

**Nothing in this project's locked dependency closure does either.** There is no
`cryptography`, no `pyjwt`, no `joserfc`, no `authlib`; checked against the
project virtualenv rather than assumed. [SPEC §7.1](../SPEC.md) names `pylti1p3`
for the *tool* side, which will bring a JOSE stack with it in E1, but E1 has not
happened and the tool is not this service.

Adding one is not the small change it appears to be.
[ADR 0005](0005-dependency-locking.md) locks *the backend's* closure, compiled by
`pip-compile` out of `pyproject.toml` into two hash-pinned files. The mock is a
second application, and it has no lockfile of its own.

## Decision

`mock-lms/app/signing.py` generates the key pair and produces the signature using
the standard library alone: `secrets` for randomness, Miller-Rabin over `pow` for
primality, `pow` for the signature, `hashlib` for the digest, `base64` for the
encoding. `mock-lms/` takes **no dependency of its own**; its image installs the
backend's already-locked `requirements.txt` for FastAPI and uvicorn.

**The bound on this decision is as much a part of it as the decision.** It
applies to `mock-lms/` and nowhere else, because what is being protected there is
nothing: the key exists for one process, signs launches for a fake platform, and
is thrown away. Pulse's own signing key — E1's, for the tool half — is a real
credential and belongs to a real library, brought in through `pyproject.toml` and
`make lock` like everything else.

## Alternatives rejected

**`cryptography` in `[project] dependencies`.** The cleanest code, and it ships a
compiled cryptography stack in the production backend image for the sake of a
development-only service. E1 will add it for a reason of its own, and adding it
now under E0-14's name would mean the runtime closure carried it for a whole
epic with nothing importing it.

**`cryptography` in the `dev` extra.** Keeps it out of the runtime closure, and
then the mock's image has to install `requirements-dev.txt` — pytest, hypothesis,
testcontainers, docker — to reach it. A test toolchain in a service image is
worse than the arithmetic below.

**A second lockfile for `mock-lms/`.** Honest, and out of proportion: a second
`pip-compile` input, a second `make lock` target, a second `pip-audit` target in
the supply-chain job, and an ADR of its own, all inside a ticket about launches.
It is the right answer the moment the mock needs a third-party library for
something that is not arithmetic — E0-15's NRPS and AGS stubs are the next place
to ask.

**An unpinned `pip install cryptography` in the mock's Dockerfile.** Rejected on
`CLAUDE.md`: no floating ranges, no unpinned tool versions.

**A smaller key, to generate faster.** Rejected because it would teach a reader
that a mock key is a different kind of key. 2048 bits is what a real platform
uses and what every JOSE implementation accepts.

## Consequences

**Key generation costs time.** Measured on a development machine: 0.29–0.80 s per
2048-bit key, median about 0.31 s. The integration suite starts roughly two dozen
platforms, so it pays about ten seconds. If that becomes the slowest thing in the
suite, the fix is fewer platform starts, not a smaller key.

**The signature is checked by an independent implementation.** The verifier in
`tests/conftest.py` is written from RFC 8017 by the test author, out of `pow` and
`hashlib`, and it is exercised in both directions — against a token from a second
platform and against a tampered payload. So a defect in the signing arithmetic
here fails a test rather than producing a token that only this repository
accepts.

**A reviewer will read `signing.py` as hand-rolled cryptography, and should.**
The answer is the bound above: it is a test fixture that happens to be shaped
like a key. If that bound ever stops holding — if anything outside `mock-lms/`
imports this module, or if the mock is ever reachable from a deployment — this
record is wrong and the dependency question reopens.

**`mock-lms/` has no dependency of its own to audit.** `pip-audit` and the
license gate read the two lockfiles, and this service adds nothing to either.
That is a real benefit and it is also the thing that makes the cost above worth
paying twice: the second application in this repository ships with no supply
chain.
