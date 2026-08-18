# Entry 28. A driver that could only speak correctly made the invalid half of every guard unreachable

**Caught: 0**

*Part of [docs/MISTAKES.md](../MISTAKES.md). The number is this entry's name — citations point at it, so it never changes.*


**What happened.** E0-16's mock OIDC provider answered a 500 to two malformed PKCE
values: a `code_verifier` outside ASCII raised when the token endpoint hashed it,
because RFC 7636 computes the challenge over ASCII octets, and a `code_challenge`
outside ASCII — accepted and stored by the authorization endpoint an hour of
protocol earlier — raised when the same redemption compared it with
`secrets.compare_digest`, which refuses two strings it cannot treat as ASCII.

Both were found by the implementer reading its own finished code. **Nothing in the
suite could have found either**, and the reason is structural rather than an
oversight: every PKCE value the suite sends is built by `pkce_pair` in
`tests/conftest.py` out of `secrets.token_urlsafe`, whose alphabet is exactly the
unreserved set both guards accept. Seven refusal tests across the two provider
modules — a replayed code, a mismatched verifier, an absent verifier, an
unregistered redirect URI, two launch-only identities, a launch-only role — all
sending values that were well formed by construction. The suite read as covering
the refusal path thoroughly, and could not enter the half of it that was broken.

**Root cause.** A driver that impersonates a correct client is, by construction,
incapable of misbehaving. It is written to make the working path work — build the
challenge, echo the state, sign the launch — and every test that reaches the
system through it inherits that competence, including the tests whose whole
subject is what happens when a client gets something wrong. Nothing marks the
gap: there is no narrowed bound to notice and no claim to read a strategy
against, because no test names the malformed case at all. The absence is in the
fixture, and it is invisible from every file that uses it.

**This is entry 15's family and a different mechanism, which is why it is its own
heading.** There, a property test *stated* the case its generator could not
produce, and the two could be read against each other inside one file. Here there
is no such pair — the tell is not a bound that looks too small but a fixture that
looks correct. The blast radius differs too: a narrowed strategy weakens one
property, while a driver's competence weakens every refusal in every module it
serves, all in the same direction. Entry 15 split from entry 3 on exactly this
reasoning about mechanism.

**It had already been written down once, and nothing acted on it.** E0-14's own
`tests/integration/test_mock_lms_launch.py` docstring says "what E1 will
additionally need is a way to mint a deliberately wrong launch", which is this
rule stated as a future need — and the launch driver still cannot mint one, so
the platform side of the repository is in the same position today. A hazard named
in a docstring is a note; nothing turns it into coverage.

**Consequence.** Two crashes reachable by any client, in the service whose stated
job is to teach E1's client what a strict provider does. E0-16's definition of
done says "an identity provider that is lenient in the wrong place teaches the
tool-side code bad habits"; a provider that raises where it should refuse teaches
E1 to expect a 500 from a shape every real IdP answers with a 400, and the
crashes were reachable from the outside by a client sending one wrong character.

**Rule.** **When a fixture speaks a protocol, ask what it cannot say.** Enumerate
the values the driver builds for the system under test, and for each one ask
whether any test could send a malformed version — not a *wrong* version, which
drivers usually do allow, but one that violates the shape. A refusal criterion is
only asserted over the inputs the driver can express, so where it cannot express
the malformed shape, either give it a way to send one or write the constant out
by hand in the test module and say why.

The cheap version is a search with a reliable signal: **every value a driver draws
from `secrets`, `uuid4`, a formatter or a specification-conformant builder is a
value no test can malform.** Those are the parameters to write bad constants for.
And when a fixture's own docstring says a future ticket "will need a way to send a
deliberately wrong X", that is this entry firing — treat it as a missing fixture
now rather than a note for later, because the ticket that inherits it will build
against a driver that is still polite.

---
