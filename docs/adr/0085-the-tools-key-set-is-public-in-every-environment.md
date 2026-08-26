# 0085 — The tool's key set is public in every environment, and its `kid` is the key's thumbprint

## Context

E1-06 part 4 gives the tool a JWKS route: a platform verifies the
`client_assertion` this tool signs against a key set it fetches from the tool, so
a tool that publishes none can make no service call anywhere. It is this
project's first cryptographic production endpoint, and the ticket marks it as the
⚠ half for that reason.

[ADR 0082](0082-the-tools-signing-key-lives-in-the-database.md) already decided
custody: one row, private PEM only, public half and `kid` derived on read, no
rotation. It decided nothing about the route, because in E1-05 there was none.
Three questions are left, and a reasonable engineer would answer at least the
first differently:

- **Who may fetch it.** This repository gates by environment out of habit —
  `/docs` (ADR 0074), `/dev` (ADR 0079) and the demo seed (ADR 0063) are all
  keyed on `ENVIRONMENT`, and a new route written beside them inherits the gate
  without anybody deciding to.
- **What identifies the key.** Any stable string satisfies a `kid`.
- **What a deployment with no key answers.** ADR 0082 makes that a real state:
  the key is written by the demo seed, which runs only in development.

## Decision

**`GET /lti/jwks`, registered unconditionally, on `app/api/lti.py`'s router.** No
environment gate, no authentication, in every deployment. A tool whose key set
answers 404 in production cannot be registered at a real platform at all, and
there is nothing here to protect: every value the route serves is public by
construction, which is what a public key is for.

**One key, and its `kid` is its RFC 7638 thumbprint**, computed on read from the
same three members the platform will compute it from — `e`, `kty`, `n`,
lexicographic, no whitespace. A platform selects a verification key by `kid` and
this tool writes one into every assertion header it signs; any stable string
works right up until those two values are computed in different places.

**The JWK is assembled member by member from the public numbers**, never
filtered out of a serialised key pair. `cryptography` will hand back a private
key's members one call from the public ones, and the difference is a `d` beside
the modulus in a document that passes every other check.

**A deployment holding no `tool_signing_key` row answers 503**, with a body that
says only that this deployment publishes no key set.

## Alternatives rejected

**Gating the route on `ENVIRONMENT=development`.** The shape three neighbouring
features use, and the one a reader would expect. Rejected because it makes the
tool unregistrable everywhere it matters, and the failure is invisible until a
platform administrator pastes the URL in: nothing in the suite would notice,
because every other test runs in development. The parametrised pair in
`test_the_tool_publishes_its_key_set.py` exists to keep it that way.

**Answering an empty key set where there is no row.** Conformant — RFC 7517
permits an empty array — and it keeps a 200 on a route a platform may poll.
Rejected because an empty set is a document a platform *accepts and stores*, and
the failure then arrives hours later at that platform, as an assertion refused
for a reason that names no key. A 503 fails where the missing thing is.

**Caching the derived JWK for the process.** The PEM does not change and the
derivation costs a key load per request. Rejected on the same ground ADR 0082
rejects storing the public half: a cache is a copy of something derivable, and
this one would go stale exactly when the row is replaced — the one moment the
document must be right. It is a cheap thing to add later, with a measurement
behind it.

**Serialising the key pair and removing the private members.** One call, and it
produces the same document today. Rejected because it makes correctness a
question of whether the removal list is complete: RFC 7518 defines seven private
members, a future key type may define more, and a member nobody thought to filter
is the tool's identity served to whoever asked. Nothing here ever holds a private
member to leave out.

**Making the path configurable.** Rejected as a knob with one correct answer: it
is a public URL a platform is registered with, so a spelling that can move is a
spelling that changes under whoever already stored it.

## Consequences

**An unauthenticated route now reads the database on every request.** It is one
indexed read of a one-row table and it holds no lock, but it is a public endpoint
that does work, which nothing else in this tool's surface is yet. If that ever
matters the answer is the per-process cache rejected above, with a measurement.

**`pulse_app` can now read the tool's private key.** That is the widening
`tool_signing_key_grants_v001.sql` carries and ADR 0082 anticipated — "the grant
lands in E1-06 with the code that spends it". `SELECT` alone, so the role cannot
rotate the tool's identity, and the PEM never leaves the process it is read into:
what this route publishes is two integers.

**Rotation is still unbuilt** and this route now makes its absence visible. A
platform that has fetched this document holds one `kid`; replacing the row
changes both the `kid` and the key with no overlap window, and every assertion
signed by the old key fails from that moment. ADR 0082 owns that question.

**A non-development deployment answers 503 here until somebody supplies a key.**
That is ADR 0082's deliberate gap made loud rather than a new one, and it is
carried with a done-when in `docs/tickets/e1/deferred.md`.
