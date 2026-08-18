# 0059 — Each mock ships its own copy of the standard-library RSA signer

**Status:** Accepted
**Date:** 2026-08-17
**Tickets:** E0-16

## Context

[ADR 0035](0035-the-mock-platform-signs-with-standard-library-rsa.md) settled
that the mock LTI platform signs with an RSA implementation written out of `pow`
and `hashlib`, because nothing in this project's locked dependency closure signs
a JSON Web Signature and the mock has no lockfile of its own.

E0-16's provider needs the same thing for the same reason: an `id_token` signed
RS256, a JWK Set publishing the public half, and a `kid` derived from the key.
`mock-lms/app/signing.py` already does exactly that, in 260 lines that took a
careful reading of RFC 8017 and RFC 7638 to get right. Copying it is duplication
of the kind DRY exists to prevent.

The obvious alternative — one shared module both mocks import — runs into how
the two are actually loaded. [SPEC §13](../SPEC.md) gives each mock a package
called `app`, so there are three packages of that name in this repository, and:

- each image holds exactly **one** of them, at `/app/app`, and installs no other
  Python code from this repository (`mock-lms/Dockerfile`, `mock-idp/Dockerfile`);
- the test suite imports a mock by putting a scoped finder on `sys.meta_path`
  that resolves `app` — and only `app` — out of that mock's directory
  (`MockPackageFinder` in `tests/conftest.py`), because an editable install of
  the backend registers a finder of its own and `sys.meta_path` is consulted
  before `sys.path`.

A shared module would therefore have to be a fourth top-level package, on the
import path of two images *and* of the test process, resolved before the
backend's finder. `tests/` is written by a different agent under a different
ticket, and nothing in the suite puts anything but `app` on that path.

## Decision

`mock-idp/app/signing.py` is a copy of `mock-lms/app/signing.py`. Everything
below the module docstring is identical, and each docstring says so and names the
other, so `diff mock-lms/app/signing.py mock-idp/app/signing.py` is the check
that they have not drifted.

The duplication is bounded to this one module. Nothing else is copied between
the mocks: the seeds, the pages, the configuration and the protocol logic are
different programs that happen to sit beside each other.

## Alternatives rejected

**A shared top-level package, e.g. `mockjose/`, imported by both.** The right
answer if the import machinery allowed it. It would need: a `COPY` into both
images, a `sys.path` entry in both containers, and a change to
`tests/conftest.py`'s finder so the suite can resolve it — which is a file this
ticket may not edit, and a change that would make every mock's import depend on
a second path rule.

**Put it in the backend and install the backend into both mock images.** This is
the arrangement both mock Dockerfiles exist to prevent: an image holding two
packages called `app` resolves `import app` by whichever wins the path. It would
also ship a development-only signer inside the production application, which is
exactly what ADR 0035's bound forbids.

**A published package on PyPI.** For 260 lines of throwaway-key arithmetic, in a
repository whose dependency policy is hash-pinned lockfiles compiled from
`pyproject.toml`, for a service that is not deployed.

**Have the provider fetch its key from the platform.** Absurd on its face, and
worth writing down because it looks superficially tidy: it would make two
independent fake institutions share one identity, and it would couple the two
mocks at run time so that neither could start without the other.

## Consequences

**Two copies can drift, and nothing automated says so.** A `diff` is the whole
guarantee. That is a real cost and it is accepted because the alternative is a
fourth import path in three places; if a third mock ever appears, this trade
should be re-opened rather than repeated.

**A fix to one is a fix to both, by hand.** Anyone correcting the padding, the
primality test or the thumbprint has to apply it twice, and the pull request that
does it should say so. The two copies are byte-identical today precisely so that
"is this the same code?" is answerable in one command.

**ADR 0035's bound now covers two directories.** Its decision is bounded to
`mock-lms/`; this record extends the same bound to `mock-idp/` on the same terms
and for the same reason, and neither bound reaches `backend/`. Pulse's own
signing key, when E1 introduces it, is a real credential and belongs to a real
library.
