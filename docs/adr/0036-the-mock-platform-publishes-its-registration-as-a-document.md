# 0036 — The mock platform publishes its registration as a document keyed by column

**Status:** Accepted
**Date:** 2026-08-16
**Tickets:** E0-14

## Context

E0-14's scope asks for "seeded platform registration values matching what
`lti_platform` from E0-08 expects, so a developer can register the mock in one
step". It names no interface, and [SPEC §9.2](../SPEC.md) does not either. The
test author wrote no test for it rather than inventing a path, and said so.

Four values are needed to register a platform: the issuer, the client ID, the
deployment ID, and the JWKS URL — the columns
[`lti_platform` and `lti_deployment`](../../backend/app/models/lti.py) hold. Two
more are needed the moment a launch is validated: the authorization endpoint and
the OIDC discovery URL. E0-08's own module docstring says those two arrive "with
the code that calls them", which is E1's.

## Decision

`GET /registration` returns a JSON object whose **keys are the column names** the
values go into — `issuer`, `client_id`, `deployment_id`, `jwks_url` — plus
`authorization_endpoint` and `openid_configuration`. The launch page renders the
same values in a definition list, outside the form.

Column names rather than protocol terms, so `jwks_url` and not `jwks_uri`: the
audience is someone filling in a row, and "one step" should not include
translating between two vocabularies for the same thing.

Two audiences, one source. A human reads the launch page; E0-17's seed script and
anything else that wants to register the platform without a browser reads the
JSON. Both are built by `registration_values()` in `mock-lms/app/pages.py`, so
they cannot disagree.

## Alternatives rejected

**Nothing at all — read the values off the launch page's hidden form fields.**
This is what `tests/conftest.py` does, and for a test it is right: the OIDC
third-party-initiated login request genuinely is the platform announcing itself.
As a developer interface it is not: `jwks_url` is not in that request, and
scraping hidden inputs out of HTML is not "one step".

**Only the OIDC discovery document.** It is served, and it carries the issuer,
the authorization endpoint and `jwks_uri` — but not the client ID or the
deployment ID, which are registration values rather than platform metadata. A
developer would still be reading two documents.

**A `POST` from the mock into the tool's admin API to register itself.** No such
API exists, it would couple a development-only service to the tool's
authentication, and it would make the mock a client of the thing it exists to
launch. E0-17 owns seeding.

**Environment variables echoed into the container log at startup.** Discoverable
only by whoever was watching, and it establishes "print configuration at startup"
as a pattern in a repository whose §10 forbids identifiers in logs.

**A `.env.example` block a developer copies.** The mock's values are not
`app.config.Settings` fields and are not interpolated by Compose, so
`tests/unit/test_env_example_sync.py` refuses them. See
[ADR 0037](0037-the-mock-platform-is-configured-by-compose-literals.md).

## Consequences

**The document is a record that can go stale**, in exactly the way
`docs/MISTAKES.md` entry 1 describes. It is built from the settings object rather
than written out, so a changed issuer moves both the launch and the document; but
a *new* registration field added later has to be added here, and nothing fails if
it is not. The next ticket to touch registration should check this list against
`lti_platform`'s columns.

**No endpoint here is advertised unless it is served.** There is deliberately no
`token_endpoint`, because there is no token endpoint until E0-15 builds the
Advantage services. An advertised endpoint that answers nothing is worse than an
absent one: it fails at the point of use, in a tool, with a 404 that reads as the
tool's bug.

**It is one more unauthenticated endpoint on a service that must not be
deployed.** It publishes nothing secret — every value in it is public by design,
and the JWKS URL serves public keys — but it is another reason the boundary in
[ADR 0038](0038-the-mock-platform-ships-in-the-base-compose-file.md) has to hold.
