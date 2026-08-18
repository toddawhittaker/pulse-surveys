# 0058 — The mock provider publishes its registration and its seed as one mock-only document

**Status:** Accepted
**Date:** 2026-08-17
**Tickets:** E0-16

## Context

An OIDC authorization request names a `client_id` and a `redirect_uri`. E0-16
spells neither, and [SPEC §9.2](../SPEC.md) does not either — it asks for
"standards-compliant discovery/authorize/token/JWKS with seeded leadership, Care
and admin identities" and stops there. So a client cannot start a flow against
this provider without learning two values from somewhere, and today the only
"somewhere" is reading `mock-idp/app/config.py`.

The test author raised this as a gap in the ticket rather than inventing a path:
`MockIdentityProvider.registration()` in `tests/conftest.py` looks in the three
places a reasonable implementation would publish them — a JSON document the
provider serves, a form field on one of its own pages, or the `mock-idp`
service's Compose environment — and fails by name if none of them does.

Two later tickets need the same two values, which is what makes this a real gap
rather than a test's convenience. E1 builds the tool side of this login and has
to configure a client. E0-18 drives the whole door in a browser.

E0-16 also seeds "one person who holds **both** a Care assignment and an
instructor assignment", and says E0-10 and E0-18 reuse that fixture. Nothing in
the ticket says how a test identifies her — and by construction she cannot be
identified by signing in, because the instructor half is exactly the half this
door does not act under.

## Decision

`GET /mock/registration` returns one JSON document holding **both**: the
registered client, and every seeded identity with the assignments behind it.

The client half is keyed with protocol spellings — `client_id`, `redirect_uri`,
`jwks_uri`, `token_endpoint_auth_method`, `code_challenge_method` — because the
audience is whoever configures an OIDC client library.
[ADR 0036](0036-the-mock-platform-publishes-its-registration-as-a-document.md)
keyed the platform's document by *column* name instead, and the difference is
deliberate: there the audience fills in `lti_platform`'s columns by hand, and
here there is no such table until E1 builds one.

Each seeded identity carries its `sub`, its label, its address, the roles a
session for it states, the roles it holds that **use the other door**, every
assignment with the node it is scoped to, and its LMS user ID where it has one.
That last pair is what makes the two-hat person findable: she is the person whose
`launch_only_roles` is non-empty, and her `lms_user_id` names the user
`mock-lms/app/seed.py` seeds as the instructor of every section.

The path sits under `/mock/`, the prefix
[ADR 0047](0047-the-posted-score-readback-is-a-mock-only-route.md) established
for a route no real service serves. The index page renders the same values from
the same functions, so a human and a script cannot be told different things.

**Six of those members are a contract, and the rest are prose.** A later ticket
may depend on `client_id`, `redirect_uri`, and on each entry of `users` carrying
`sub`, `roles`, `launch_only_roles` and `lms_user_id` — those six are what E1's
login work and E0-18's browser paths were given this document for, and changing
the name, the type or the meaning of any of them is a breaking change that has to
move its callers in the same pull request. Everything else here — `label`,
`email`, `assignments` with their scope strings, and the endpoint URLs a client
should be reading out of the discovery document instead — is documentation for a
human, and may be reworded or dropped without ceremony.

The line is drawn here rather than left to whoever depends on it first, for the
reason `docs/MISTAKES.md` entry 2 gives: E0-18 is about to build on
`launch_only_roles` and `lms_user_id`, and a field depended on by a later ticket
and asserted by nothing is a field that gets renamed by somebody tidying a
document. With the set named, a test can hold exactly it — which is what E0-16's
own suite deliberately does not do, since pinning members from the test side
before anything settled them would have been the tests choosing the contract.

## Alternatives rejected

**`GET /registration`, without the prefix.** The obvious spelling, and it
collides with the protocol: `registration_endpoint` is RFC 7591 dynamic client
registration, which this provider does not implement. A path spelling
"registration" outside the mock namespace either has to be advertised as that
endpoint — a record asserting something untrue, which
[ADR 0036](0036-the-mock-platform-publishes-its-registration-as-a-document.md)
already refuses for the platform's absent `token_endpoint` — or be an
unadvertised protocol-looking route for every client to wonder about.

**Compose literals only, with no document.** The values *are* Compose literals
([ADR 0037](0037-the-mock-platform-is-configured-by-compose-literals.md), and
this ticket reaches the same answer), so a test could read them out of
`docker-compose.yml`. That works for a test running in this repository and for
nothing else: E0-18's browser has no Compose file, and a client configured from
a file it does not read is a client configured by hand.

**Hidden form fields on a page, as the mock platform's launch page does.** Right
for the platform, because there the OIDC third-party-initiated login request
genuinely *is* the platform announcing itself, so the fields are the protocol.
Here there is no such form: a login begins at the client, and a "start a login"
form on this provider's own page could not carry a PKCE challenge, because the
verifier belongs to whatever will redeem the code.

**Two documents — a registration and a seed.** Tidier on paper. It doubles the
number of things a later ticket has to know the name of, for two halves that are
always fetched together, and the seed half is the one nobody would think to look
for.

**Nothing, and let E1 read the source.** This is the status quo the test author
named, and it is a gap rather than a style: the values would then be learned by
reading a Python module, which no browser test can do, and every client that
learned them would be a second place they are written down.

## Consequences

**The document is a record that can go stale**, exactly as ADR 0036 says of the
platform's. It is built from the settings object and the seed rather than written
out, so a changed client ID or a renamed person moves both the flow and the
document — but a *new* field added to either has to be added here, and nothing
fails if it is not.

**The six contract members bind this ticket's document to two later ones**, which
is the cost of naming them: a rename now moves E1's login work and E0-18's specs
too. That is the intended trade — the alternative is those tickets depending on
whatever the document happens to say, which is the same coupling with nobody
responsible for it. The set is deliberately small, and `assignments` is outside it
so that the seed can grow a person or a scope without touching anything.

**One value in it is a claim about the other mock.** `lms_user_id` names a user
in `mock-lms/app/seed.py`, and nothing checks that it still exists: if the
platform renames its instructor, this document goes on asserting a
correspondence that has stopped being true (`docs/MISTAKES.md` entry 1). It is
written in one constant, `LMS_INSTRUCTOR_USER_ID`, so the repair is one line —
and E0-18 is the ticket that will notice, because it is the one driving both
doors as the same human.

**It is one more unauthenticated endpoint on a service that must not be
deployed**, and this one publishes the identities rather than only the
configuration. It publishes nothing secret — the people are invented, the
addresses are at an RFC 2606 reserved domain, and there is no credential
anywhere in this service to publish — but it is another reason the boundary in
[ADR 0038](0038-the-mock-platform-ships-in-the-base-compose-file.md) has to keep
holding.

**A later ticket that seeds the same institution into Pulse's database owns the
correspondence.** The scopes here are prose — "the College of Sciences", "BIOL
215" — and nothing resolves them against E0-17's seed. If E0-18 needs the two to
be the same institution, that is E0-17's rows and this document's `assignments`
being read together, and the ticket that does it should say so rather than
assume it.
