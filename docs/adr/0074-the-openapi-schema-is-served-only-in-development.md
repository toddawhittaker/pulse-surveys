# 0074 — `/docs` and `/openapi.json` get routes only when `ENVIRONMENT` is `development`

**Status:** Accepted
**Date:** 2026-08-21
**Ticket:** [E0-18](../tickets/e0/E0-18-e0-exit-smoke.md)

## Context

`create_app()` built `FastAPI(...)` with neither `docs_url` nor `openapi_url`
passed, so FastAPI's defaults applied and the interactive documentation and the
schema were served to anyone who asked. That was harmless while the schema
described `/healthz` and nothing else.

E0-18 adds the first real routes, and every epic after it adds more. An OpenAPI
schema is a complete list of what an application answers on, with the shape of
every request and response beside it — served, in a launched LTI tool, to a
browser inside somebody's LMS.

[SPEC](../SPEC.md) does not decide this. §6.3 enumerates the configuration
surface and no documentation setting is in it; §7.1 says the schema exists and
that the future MCP server is built from it; §13 has a client generator that
calls `app.openapi()` in process. What §6.2 and §5.5 *do* establish is that route
enumeration is not neutral in this product: §6.2's Care surface and §5.5's
roll-ups are the two places where knowing a URL exists is itself information
about who can re-identify a student and about which sections are being compared.

## Decision

**Serve the routes only when `settings.environment` equals exactly
`"development"`.** `create_app` passes `docs_url`, `redoc_url` and `openapi_url`
as `None` for any other value.

The value compared against is `app.config.DEVELOPMENT_ENVIRONMENT`, a constant
this ticket adds to `config.py` because there are now three readers of it —
`app/db.py` before it lets the engine echo SQL, `scripts/seed.py` before it will
run at all ([ADR 0063](0063-the-demo-seed-runs-only-in-a-development-environment.md)),
and this.
E0-18 migrated neither of the other two onto it, because doing it there would
have put an unrelated change in an auth pull request; **E0-37 item 2 did**, so
all three readers import this constant now.

**The schema stays producible either way**, and that is the half that is easy to
get wrong: `openapi_url=None` removes the *route*, not the generation.
`app.openapi()` returns the same document under every environment, which is what
§7.1's MCP server and §13's client generator need.

## Alternatives rejected, and what each costs

**Leave them public.** Defensible: this is a single-tenant product, the schema
describes an API that enforces its own authorization at every endpoint (§2.1's
chokepoint), and a route list is not a credential. It also costs nothing and
keeps `/docs` available when debugging a deployment, which is exactly when
somebody wants it. Rejected because the cost of gating is one comparison, and
because "the endpoints enforce authorization" is a claim about code that has not
been written yet for any epic past this one.

**Gate on the authenticated actor** — serve the schema to an admin, refuse it to
everyone else. The most consistent answer, and the one that keeps `/docs`
working in production for the people §6.3 gives the admin console to. Rejected
as E1-shaped: there is no session, no actor and no authenticated request in E0,
so building it would mean building the session model this ticket's boundary
section explicitly gives to E1. It remains the right answer later, and this
record is not an argument against it.

**Gate on a separate `SERVE_API_DOCS` flag.** Rejected on the rule against knobs
— "no configuration knob for something with one correct answer", stated in
[`docs/AGENTS_INTENT.md`](../AGENTS_INTENT.md) (attribution corrected 2026-08-22:
this cited `CLAUDE.md`, which holds process only). There is one correct answer per
environment, the environment is already a variable, and a second flag is a way for
a deployment to be documented as gated while being open.

## Consequences

- A deployment that leaves `ENVIRONMENT` unset fails at startup — the field is
  required — rather than silently serving the schema. A deployment that sets it
  to `dev`, `local` or `Development` gets the closed gate, because the
  comparison is exact and case-sensitive. That is the safe direction of a
  vocabulary nothing enforces, and `.env.example` documents the three words.
- `/docs` is unavailable in staging and production, which is where somebody will
  eventually want it. The unblocking move is the rejected alternative above, not
  a flag.
- The generated frontend client (§13) is unaffected: it calls `app.openapi()` in
  process, and that script does not exist yet.
- For this to keep working, nothing may start deriving the schema from the HTTP
  route. `tests/unit/test_docs_exposure.py` holds all three halves — served in
  development, not served outside it, and produced in process either way.
