"""The in-repo mock AI provider (SPEC §9.2, §13).

This package is a **test harness**, not a product surface. Pulse depends on three
things it does not run: an LMS to be launched from, an identity provider to log
in through, and a model to classify a comment with. `mock-lms/` and `mock-idp/`
stand in for the first two; this stands in for the third, so that an end-to-end
run is self-contained and no ordinary run of this stack calls a model anybody
pays for.

**It classifies by published rule, not by judgement.** `app.rules` holds the
whole vocabulary — four deliberately wrong answers, three forced verdicts, and a
character threshold — and `GET /mock/rules` serves it, so a test aims at the
mock's own statement of what it does rather than at a second copy of it (E2-07's
third acceptance criterion). `mock-ai/README.md` says the same thing in prose for
a person.

**It is a fourth package called `app`.** The backend's package, the mock
platform's and the mock provider's have the same name (SPEC §13 names all of
them), and all four are importable in a test process. Nothing here may import
`app.*` lazily inside a request handler: an editable install of the backend
registers a meta-path finder, `sys.meta_path` is consulted before `sys.path`, and
a late `from app.x import y` therefore resolves to whichever of the four the
interpreter happens to prefer. Every import in this package is at module scope,
where the test fixture's scoped finder is still installed
(`docs/adr/0039-the-two-app-packages-are-typechecked-in-two-runs.md`).

Nothing in here is safe to reuse outside this directory:

- **it is not a model.** It answers `substantive` to anything over a character
  count and `insufficient` to anything under it, which is SPEC §3.3's fail-open
  floor wearing a provider's clothes. A stack pointed here is a stack that is not
  classifying;
- **it authenticates nobody.** There is no credential anywhere in this package.
  It answers a completion for whoever asks, which is what makes it drivable from
  a test and what makes it unfit for anywhere else;
- **it can be told to fail.** A comment carrying `mock-ai:503` gets a 503 and one
  carrying `mock-ai:500` gets a 500, so anyone who can write a survey comment can
  choose what this provider answers.

That last property is why it must never be what a deployment talks to. The
boundary is the one
`docs/adr/0038-the-mock-platform-ships-in-the-base-compose-file.md` draws for the
platform, and it holds here for the same reasons — this service holds nothing,
reaches nothing, and publishes no port outside development — plus one of its own:
`app.config.Settings` refuses an `AI_PROVIDER_BASE_URL` whose host is `mock-ai`
anywhere `ENVIRONMENT` is not `development`
(`docs/adr/0113-the-mock-model-provider-is-development-only-and-selects-in-band.md`).
"""

__all__: list[str] = []
