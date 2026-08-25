# 0084 — The mock platform's token endpoint bounds an assertion at five minutes, and refuses in RFC 6749's vocabulary

## Context

E1-06 gives the mock platform the OAuth 2.0 client-credentials grant, so that
E1-11 can build a conformant service client against it. The specifications fix
the shape of the exchange — RFC 6749 §4.4 the grant, RFC 7523 §2.2 the
`client_assertion` profile, RFC 6749 §5.1 and §5.2 the two response bodies — and
leave a platform to decide five things that a client is then built against.
`docs/SPEC.md` is silent on all five, and the ticket says so about one of them in
as many words: "an assertion with no `exp` or one longer-lived than the short
bound the mock enforces (minutes, not hours; **the exact bound is the
builder's**, asserted in a test)".

The five are decided together because they are one surface. A client that meets
this endpoint discovers all of them at once, and each of them is a thing E1-11
either satisfies or is refused by.

## Decision

**1. An assertion may claim to live at most 300 seconds, measured `exp - iat`.**
A tool-signed assertion is a bearer credential — whoever holds it can spend it at
this endpoint until it expires — so an unbounded `exp` is a credential that stays
usable wherever it leaks. Five minutes covers any clock skew a real deployment
has. It is measured against the assertion's own `iat` rather than against the
platform's clock, so the boundary is exactly where the number says and a slow
request cannot move it; an assertion carrying no `iat` is measured from now.

**2. `aud` must be the token endpoint's own advertised URL.** Not the issuer,
which is the value most likely to be compared against by accident, and which
would let an assertion minted for any endpoint on this platform be spent at this
one. A list-valued `aud` is accepted if the token URL is in it, which is what
RFC 7519 §4.1.3 allows.

**3. Every refusal is 400 with the RFC 6749 §5.2 code that says why**:
`invalid_request` where the request or the assertion is missing something it must
carry, `invalid_client` where an assertion arrived and does not authenticate the
client, `invalid_scope` where the platform will not grant what was asked for,
`unsupported_grant_type` for anything but `client_credentials`. 400 and not 401,
including for `invalid_client`: §5.2 makes 400 the status and carves out exactly
one exception, a client that "attempted to authenticate via the `Authorization`
request header field", which a `client_assertion` in the form body is not.

**4. The assertion is verified against every key in the tool's published set**,
which the platform fetches from a configured address while the request is being
verified. Not selected by the header's `kid`: the tool publishes one key (ADR
0082), and selecting by `kid` invites the failure where a key is *found* and the
token is then trusted because one was. The address is a sixth setting,
`MOCK_LMS_TOOL_JWKS_URL`, stated as a Compose literal beside the two the platform
already holds about the tool it serves (ADR 0037).

**5. The issued access token is a compact JWS signed by the platform's issuer
key**, carrying the granted scope and an hour's expiry.

## Alternatives rejected

**Accepting the issuer as `aud` as well as the token URL.** Some real platforms
do, and a client built against one of those would fail here. Rejected because the
audience is the only thing stopping an assertion being replayed at a different
endpoint of the same platform, and a mock that accepted the looser value would
teach E1-11 a habit that a stricter platform refuses — which is the direction of
error this whole ticket is trying to avoid.

**Measuring the lifetime as `exp - now`.** One fewer claim to read, and robust to
an assertion with no `iat`. Rejected because the boundary then moves with how
long the request took: an assertion minted at the bound and delivered a second
later measures one second under, and the same assertion one second past the bound
measures at it. A bound whose test is a coin flip on a loaded machine is not a
bound.

**401 for `invalid_client`.** The intuitive reading, and what a good deal of
deployed software does. Rejected on §5.2's own text: the 401 is conditioned on
the `Authorization` header, and answering 401 here would also invite a client to
retry with an `Authorization` header this endpoint does not read.

**Selecting the verification key by the header's `kid`.** What a platform with
many registered tools must do, and what this one will need if a tool ever
publishes two keys. Rejected today because it is one line from the defect it
resembles — find a key by `kid`, then answer 200 — and because with one published
key it buys nothing: a wrong `kid` beside a good signature is a tool that has
rotated, not an impostor.

**Fetching the tool's key set once at startup, or caching it.** What a real
platform does, and it would make the endpoint answer without an outbound request.
Rejected because a mock exists to be verified against: a cached key set makes a
tool's key change invisible for the cache's lifetime, and E1-11 debugging a
refused assertion would be debugging this platform's cache. One HTTP call on a
development machine is not worth the state.

**An opaque random access token.** Simpler by a line. Rejected because nothing
could ever check it: E1-11 makes the Advantage services require a token, and a
random string means this platform must remember every token it has issued — a
store, and a mock that behaves differently after a restart. A JWS the platform
already knows how to mint is checkable with no memory at all.

**Deriving the tool's JWKS URL from `MOCK_LMS_TOOL_LAUNCH_URL`.** No new setting,
and right for the stack as it stands. Rejected because it is a guess about
somebody else's routing table dressed as a saving: the address a tool publishes
its keys at is a fact of the tool's registration, which is exactly what the other
two `MOCK_LMS_TOOL_*` values are.

## Consequences

**E1-11 must mint an assertion per request, or nearly.** Five minutes is not a
credential to cache and re-use for an hour, and a client that tried would be
refused after the first five minutes with `invalid_client` — a message about a
lifetime, which is why the codes are distinguishable at all.

**A tool whose clock is more than five minutes fast is refused here**, with no
allowance for skew beyond the bound itself. That is the right failure for a mock
on one machine, and it is a number a real platform would probably widen.

**This platform now makes an outbound request while serving one.** If the tool's
key set is unreachable, the token endpoint answers `invalid_client` naming the
address it tried, after the five-second timeout on the client in
`mock-lms/app/main.py`. It is the platform's only outbound fetch, and it goes
through `app.state.http` so that a test can route it.

**`scopes_supported` and what the endpoint will grant are one tuple**
(`app.tokens::ADVERTISED_SCOPES`), composed from the services' own scope
constants. Advertising a scope no token can be had for, and granting one the
document does not advertise, are two halves of one defect and neither is
expressible now.

**The Advantage services still do not require a token.** E1-06 rules that
enforcement pairs with E1-11's client, so a roster read with no `Authorization`
header still answers. What this record decides is the grant; what makes it
load-bearing is the ticket that spends it.
