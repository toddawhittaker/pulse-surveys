# 0050 — The mock roster exposes an address and no name

## Context

E0-14 seeded a platform holding no personal data at all: no `name`, no
`given_name`, no `family_name`, not invented ones. LTI 1.3 requires none of them,
so a platform that omits them is conformant and is also what a platform sends
when its privacy level is anonymous, and the property it bought was structural —
the service cannot leak what it does not hold.

E0-15 cannot keep all of that. Its scope has NRPS return "email where exposed",
§7.3 has the roster sync use email addresses "where exposed", and its definition
of done asks the security review to confirm "the seeded identities are obviously
fake, so no test fixture ever resembles real student data". So one personal field
has to arrive, and the question the ticket leaves open is whether the others come
with it. NRPS 2.0 defines all four, real platforms send all four, and a roster
carrying an address and no name looks, to anyone reading a response, like a
roster with something missing.

## Decision

The seeded roster exposes `email` and no name of any kind.

Every address is at a domain that cannot receive mail — `students.mock-lms.
invalid` and `faculty.mock-lms.invalid` — under the names RFC 2606 reserves for
exactly this. The local part is the section code and an ordinal, so an address
says which roster it came from and describes nobody.

Where a person needs to be identified to a human, they are identified by their
part in the fixture: "A student in BIOL-215-R3WW" is the label the launch page
shows, and it is a description rather than a name.

## Alternatives rejected

**Seed names as well, from an obviously-fictional set.** It is what a real roster
carries, and it is what makes the mock a more faithful reference. It loses the
one property worth more than fidelity here: a service holding no names cannot
leak a name, cannot log one, and cannot have one copied out of a fixture into
something that ships. The security note asks for identities that are obviously
fake; a name that is obviously fake today is a name somebody makes less obviously
fake tomorrow because a screenshot looked odd.

**Seed names generated from the user identifier** — `Student 04`. Same objection
with less benefit: it is a name-shaped field carrying no information the
`user_id` does not already carry, and its only effect is that E1 could build a
display path on a value no real platform guarantees.

**Expose no email either, and let E1 seed its own.** It would keep E0-14's
property whole, and it contradicts the ticket: §7.3 has the roster sync read
addresses off NRPS, and a seed exposing none leaves E1 with nothing to build the
notification path (§5.7) against. It would also make "where exposed" untestable —
the mock would only ever exercise the absent case.

**Use a plausible institutional domain** — `students.franklin.edu` or an
`example-college.edu`. Rejected outright. An address that could be delivered to
is one an outage, a misconfigured SMTP host, or a fixture copied into a seed
script eventually mails, and no test is worth that risk when RFC 2606 exists to
remove it.

## Consequences

**E1 cannot build a roster display against this mock.** Any surface that shows a
person's name has to get it somewhere else, and finding that out early is the
point rather than the cost: SPEC §4's identity separation means instructor and
leadership read paths cannot reach a name at all, so a display path built on one
would be reaching through a wall.

The mock's own claim that it "holds no personally identifiable information" is
now narrower and is written narrowly in `app.seed`: it holds addresses, and they
are unroutable by construction. `mock-lms/app/main.py`'s note about logging still
holds — nothing here logs a payload — but it now guards something rather than
nothing.

`tests/integration/test_mock_lms_seed_data.py` asserts both halves: that an
address is exposed at all, and that every one of them is at a reserved domain. A
future seed that adds a person has to satisfy the second, which is what keeps
this decision from decaying into a convention.
