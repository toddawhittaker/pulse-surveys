"""The in-repo mock OIDC identity provider (SPEC §9.2, §13).

This package is a **test harness**, not a product surface. Pulse has two entry
doors (SPEC §2): an LTI launch, which `mock-lms/` stands in for, and a web login
over OpenID Connect, which this stands in for. With both in the Compose stack an
end-to-end run is self-contained — CI needs no institutional identity provider,
and §9.2's "both entry doors are exercised in every run" is achievable.

**It is also a third package called `app`.** The backend's package and the mock
platform's have the same name (SPEC §13 names all three), and all three are
importable in a test process. Nothing here may import `app.*` lazily inside a
request handler: an editable install of the backend registers a meta-path
finder, `sys.meta_path` is consulted before `sys.path`, and a late
`from app.x import y` therefore resolves to whichever of the three the
interpreter happens to prefer. Every import in this package is at module scope,
where the test fixture's scoped finder is still installed.

Nothing in here is safe to reuse outside this directory:

- the signing key is generated per process and thrown away with it
  (`app.signing`), and the arithmetic behind it is bounded to the mocks by
  `docs/adr/0035-the-mock-platform-signs-with-standard-library-rsa.md`;
- the seeded people are invented (`app.seed`), and no real person's data ever
  reaches this service;
- **it authenticates nobody.** There is no password anywhere in this package. It
  signs a session for any seeded identity a caller picks, which is what makes it
  drivable from a test and what makes it unfit for anywhere else
  (`docs/adr/0060-the-mock-provider-authenticates-a-seeded-subject.md`).

That last property is why it must never run in a deployment. The boundary is the
one `docs/adr/0038-the-mock-platform-ships-in-the-base-compose-file.md` draws for
the platform, and it holds here for the same four reasons: this service holds
nothing, reaches nothing, publishes no port, and is trusted by Pulse only where
Pulse's own configuration names it.
"""

__all__: list[str] = []
