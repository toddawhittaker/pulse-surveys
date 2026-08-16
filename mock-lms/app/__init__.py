"""The in-repo mock LTI 1.3 platform (SPEC §9.2, §13).

This package is a **test harness**, not a product surface. It exists so that an
end-to-end run of Pulse is self-contained: `docker compose up` brings a platform
to launch from, so CI needs no live LMS and both entry doors in SPEC §2 are
exercised on every run.

**It is also a second package called `app`.** The backend's package has the same
name (SPEC §13 names both), and both are importable in a test process. Nothing
here may import `app.*` lazily inside a request handler: an editable install of
the backend registers a meta-path finder, `sys.meta_path` is consulted before
`sys.path`, and a late `from app.x import y` therefore resolves to whichever of
the two the interpreter happens to prefer. Every import in this package is at
module scope, where the test fixture's scoped finder is still installed.

Nothing in here is safe to reuse outside this directory:

- the RSA key is generated per process and thrown away with it (`app.signing`);
- the seeded people are invented (`app.seed`), and no real person's data ever
  reaches this service, which is what keeps it clear of SPEC §10's rule about
  personally identifiable information in logs;
- the service authenticates nobody. It signs a launch for whoever asks.

That last property is why it must never run in a deployment. See
`docs/adr/0038-the-mock-platform-ships-in-the-base-compose-file.md`.
"""

__all__: list[str] = []
