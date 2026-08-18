# 0060 — The mock provider holds no password: it signs in a seeded subject, and refuses by door

**Status:** Accepted
**Date:** 2026-08-17
**Tickets:** E0-16

## Context

E0-16 asks for "seeded users covering every web-login role" and "a login form
simple enough for a Playwright test to drive without brittle selectors". It
spells no credential for any of those users, and neither does
[SPEC §9.2](../SPEC.md).

Something has to decide what "signing in" means here. A real identity provider
checks a secret; this one is a fixture whose whole population is eight invented
people, and whatever it checks, a test and a browser both have to be able to
supply it.

The ticket also makes a *refusal* an acceptance criterion: "an instructor-only or
student-only identity **cannot** obtain a session here — web login is not their
door", while forbidding either role from being seeded. So the door has to be able
to say no, and it has to be able to say no about a rule rather than about a
lookup.

## Decision

**There is no password anywhere in this service.** The login form offers the
seeded identities and posts the chosen `sub`; the provider signs a session for
it.

**Who it will sign in is decided by SPEC §2's door rule, computed from a person's
assignments.** `MockPerson.may_use_web_login` is true when the person holds at
least one assignment whose role is not instructor or student, and:

- the login form offers exactly the people it is true for;
- the login handler refuses exactly the people it is false for;
- a session states exactly the roles of the assignments that opened the door.

One predicate, three readers, so the form and the handler cannot disagree, and
so the two-hat person needs no special case: her Care assignment opens this door
and her instructor assignment does not.

**A subject nobody seeded is refused.** From outside, that refusal and the door
refusal look identical, and they should: E0-16 forbids seeding an instructor or a
student here, so a launch-only identity arriving at this door is necessarily one
this provider has never heard of.

## Alternatives rejected

**Seed a password per identity and check it.** It is what a real IdP does, and
here it buys nothing and costs three things: a credential in the repository for
every seeded person (which `.env.example`'s rules and `CLAUDE.md`'s secrets
section both exist to keep out), a login form with a typed field a fixture has to
be told the value of, and a *false* lesson — that E1's tool-side code is talking
to something whose authentication strength is meaningful.

**Accept whatever `sub` the form posts, seeded or not.** One line shorter, and it
fails E0-16's criterion 7 outright: the door would sign in every identity in the
institution, instructors and students included, and the eight seeded people
would be a convenience rather than a boundary.

**Refuse by name — keep a list of launch-only subjects the provider knows about
and rejects.** It would let a test distinguish "refused as an instructor" from
"refused as unknown", which is the distinction E0-16 currently cannot assert. It
needs an instructor seeded here, which the ticket forbids in as many words, and
it would encode the door rule twice: once as a role in the seed and once as a
list of names.

**A "sign in as" query parameter instead of a form.** Drivable, and it puts the
identity in a URL — so it lands in an access log and in browser history, and it
teaches E1 that a login can be a `GET`. The form posts.

## Consequences

**This service is a signing oracle for its own fake identities**, in the same
sense the mock platform is one for its two seeded users
([ADR 0038](0038-the-mock-platform-ships-in-the-base-compose-file.md)). Anyone
who can reach the container can obtain a session as the seeded VP of Academics.
That is the intended behaviour of a test provider, and it is precisely why it
must never run where anything real trusts it — which, as with the platform, is a
property of the deployment and of Pulse's own configuration rather than of this
repository.

**The refusals cannot be told apart from outside, and the tests say so.** Both
are the required outcome — no code, no session — and the code refuses for the
right reason even though nothing can observe which reason it was. If a later
ticket ever wants that distinction observable, it needs a sentence in the ticket
saying the provider should know launch-only identities by name, and this record
is where the trade is written down.

**The door-rule branch for a seeded person who cannot use web login is currently
unreachable**, because every seeded person holds at least one web-door
assignment. It is not dead code in the sense that matters: it is the same
predicate the form reads, so it cannot silently disagree with what is offered,
and a later ticket seeding a launch-only person meets a refusal rather than a
session.

**E1 must not copy the shape.** A tool-side login that trusted whatever a form
posted would be this decision applied where it is wrong. What E1 copies from here
is the protocol — the PKCE-enforcing, single-use-code, exact-redirect-URI half —
not the authentication.
