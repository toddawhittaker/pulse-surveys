# 0066 — Seeded people are named for what they do, not for who they might be

**Status:** Accepted
**Date:** 2026-08-17
**Tickets:** E0-17

## Context

E0-17's last acceptance criterion: "Seeded people are obviously fictional; no name
resembles a real person at a real institution." Its security review repeats the
half a test can check — "no seeded person carries a real email address or anything
resembling real student data" — and
`tests/integration/test_demo_seed_script.py` says in as many words that whether a
*name* resembles a real person "is not machine-checkable and is deliberately not
asserted under a weaker reading". So the name half is a decision, held by nothing
but this record.

`person.identity_name` is `NOT NULL`, so every seeded person has one.

`design/` is the obvious source and points the other way. Its screens are full of
`Dr. A. Okafor`, `Dr. K. Sorensen`, `Dr. L. Moreau` — plausible surnames with an
initial, twenty-odd of them — and they are what a developer looking at the
prototype expects to see in the demo data. Some of those strings certainly name
real people somewhere.

## Decision

Every seeded person is named for the role they hold: `Demo Chair of Mathematics`,
`Demo Assistant Dean of Arts and Sciences`, `Demo Instructor of Calculus I`. No
invented human names, no initials, no surnames.

Three things follow from that and each is part of the decision:

- **The criterion becomes true by construction** rather than by somebody having
  checked a list of twenty names against the world. A name that describes a role
  cannot resemble a person.
- **The demo institution is legible.** A screen showing `Demo Assistant Dean of
  Arts and Sciences` reporting to `Demo Dean of Arts and Sciences` says what the
  supervision graph is doing without anyone holding a cast list in their head —
  which matters most for the two shapes E0-17 seeds precisely because they are
  easy to get wrong.
- **It is the precedent already in the repository.** `mock-lms/app/seed.py`
  describes its users as "A student enrolled in every section" and "The
  instructor of every section", and its docstring says `label` is "a description
  of the person's part in the fixture, never a name". This is the same rule on
  the Pulse side of the identity split.

Addresses follow the same shape: `chair-mathematics@pulse-demo.invalid`, at an
RFC 2606 reserved domain that cannot receive mail from anywhere.

The institution is `Pulse Demo University`, for the same reason. `design/` writes
`Franklin University`, which is a real institution.

## Alternatives rejected

**Follow `design/` and seed its names.** The strongest argument for it is
coherence: a developer comparing a screen against the prototype sees the same
data. Rejected because a demo seed is copied into staging environments by people
in a hurry, and a plausible name attached to a plausible course, in a system whose
whole subject is confidential student feedback, is the kind of screenshot that
gets read as real. The coherence is also less than it looks — the course numbers
cannot be shared either (SPEC §8's bands refuse every number in `design/`), so
the two corpora already differ.

**Generate names from a fake-data library.** Adds a dependency for a fixture, and
produces exactly the plausible-name problem above with a licence attached.
Faker's name lists are real names.

**Obviously-fake human names — `Ada Testperson`, `Bob Fixture`.** Keeps the shape
of a person and loses the legibility, since nothing on screen says which of them
is the assistant dean. It also decays: the next person to add a row picks a name
in the same style, and "obviously fake" is a judgment that drifts.

**Leave it to the reviewer.** That is where it was, and it is what this record
replaces: an unwritten rule that every future edit to `PEOPLE` has to
re-discover.

## Consequences

**`design/` and the seed disagree on names, and neither is being changed.** The
prototype is a design deliverable and this is data with a security criterion on
it. Anyone building a screen against both should expect the strings to differ,
the same way they already differ on course numbers.

**Nothing enforces this.** A future edit adding `Dr. J. Whitfield` to `PEOPLE`
passes every test in the suite, because the criterion it breaks is the one the
test module deliberately refuses to assert under a weaker reading. This record
and the comment above `PEOPLE` in `scripts/seed.py` are the whole of the guard,
and that is stated rather than left to be found out — `docs/MISTAKES.md` entry 2.

**A person's name is not a person's identity.** `person.identity_name` here is a
label; the identity that §4.1 protects lives in `user_identity`, and the seed
writes the same string into both so that the demo has something for E10's audited
reveal to reveal. Real deployments will not have that property, and nothing
should be built on it.
