# 0079 — The developer console is a real route in every environment, refused in the handler

**Status:** Accepted
**Date:** 2026-08-22
**Tickets:** none — shipped in PR #62 (`e0/interactive-testing`) alongside E0-18;
recorded by [E0-42](../tickets/e0/E0-42-the-records-the-epic-falsified.md)

Written after the fact. `GET /dev` reached the tool without a ticket and without a
record, and it is a become-any-user surface, which is the last kind of thing that
should exist only in a docstring.

## Context

E0-18 put both entry doors on the tool, and walking either one by hand means
typing a mock's URL, finding a subject identifier in a seed file, and assembling a
query string. `backend/app/api/dev.py` serves one page that removes all of that:
it reads the mock provider's published roster (ADR 0058) and offers every
web-login person as a "sign in as this person" link, plus a link to the mock LMS
launcher.

**The page is a list of identities anyone can become**, including the seeded Care
and Admin people. A production browser reaching it would be handed the worst
single page this repository could serve. [SPEC](../SPEC.md) does not mention a
developer console at all — §13's `api/` list is the screen routers plus `deps.py`
— so both the surface and its gate are decisions with nothing above them.

## Decision

**The router is included unconditionally in `create_app()`, and the handler
answers `404` when `settings.environment` is not exactly `development`.** The
comparison is `app.config.DEVELOPMENT_ENVIRONMENT`, the same constant ADR 0074
uses, and the refusal is a bare `HTTPException(404)` — indistinguishable from a
path that was never registered, so the response says nothing about whether such a
page exists.

`dev.py` is a new module, because §13's `api/` list is screen routers and a
developer console is not a screen. It builds its page from f-strings the way
`mock-idp/app/pages.py` does, since no template engine is in the locked closure,
and every interpolated value goes through `html.escape(quote=True)` even though
the roster it reads is trusted.

## Alternatives rejected

This section is a reconstruction, which is what the index page warns an ADR
written later will be. PR #62 argued the *outcome* — "indistinguishable from a
route that does not exist (ADR 0074)" — and not the choice of mechanism, so what
follows is the case for what shipped rather than a record of an argument somebody
had.

**Register the route only in development, the way ADR 0074 removes `/docs`.** The
consistent answer, and the one a reader of 0074 expects. It loses on where the
check ends up: `docs_url=None` is a constructor argument that either was passed or
was not, while this router is one `include_router` call among four and a
conditional wrapped around that call is a line somebody can move, reorder or lift
out while refactoring registration. Refusing inside the handler keeps the
environment check in the same function as the dangerous behaviour. **A later
refactor that gates routers by environment must not tidy this one into that
mechanism**, because the two failures are not the same size: a `/docs` route
registered by mistake leaks a route list, and a `/dev` route registered by mistake
hands over every seeded identity.

**Serve it behind an authenticated admin check.** There is no session, no actor
and no authenticated request in E0 — the same reason ADR 0074 rejects that answer
for `/docs` — and building one for a scaffold that E1's session model retires is
work in the wrong direction.

## Consequences

- **A deployment that sets `ENVIRONMENT` to `dev`, `local` or `Development` gets
  the closed gate**, because the comparison is exact and case-sensitive. That is
  the safe direction of a vocabulary nothing enforces, and it is the same
  behaviour `/docs` and the demo seed have (ADR 0074, [ADR
  0063](0063-the-demo-seed-runs-only-in-a-development-environment.md)).
- The refusal is asserted without a network in
  `tests/unit/test_dev_console_exposure.py`, and the development-serves direction
  with a real roster in `tests/integration/test_dev_console.py`. Both halves are
  needed: a gate that only ever refuses cannot be told from a page that never
  works.
- The console reaches the mock provider over `app.state.http` with a five-second
  timeout and renders a "mock unreachable" note at `200` rather than failing, so a
  slow mock does not look like a broken tool.
- **This is the fifth reader of the development-environment constant** — after
  `app/db.py`, `scripts/seed.py`, `app/main.py` and `app/api/deps.py`. The value
  has one definition and
  `tests/unit/test_development_environment_has_one_definition.py` is what keeps it
  that way; ADR 0074 counted three readers, which is what that number was when it
  was written.
- It ties the tool to the mock provider's registration document (ADR 0058). If
  that document's shape changes, this page degrades to its unreachable note rather
  than erroring, which is the direction that matters for a scaffold but does mean
  a broken console is quiet.
