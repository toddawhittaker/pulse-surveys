# 0099 — The mock platform requires a token on NRPS, and still does not on AGS

## Context

E1-06 built the mock platform's client-credentials grant and deliberately left
its Advantage services open, on an argument this repository has acted on twice:
"a service that started refusing before a conformant client existed would be
refusing this repository's own tests"
([`docs/tickets/e1/carried-from-e0.md`](../tickets/e1/carried-from-e0.md), "The
client-credentials grant"). That ruling named the ticket that would end it —
enforcement pairs with E1-11's client — and E1-11 shipped the client without it,
so the roster went on answering `200` to anyone who could reach the URL.

SPEC §14.3's E1 exit line asks for the other half in as many words: "a roster
read succeeds as an **authenticated service call**, not an unauthenticated GET."
A platform that answers either way proves nothing about which one happened, so
the exit clause cannot be witnessed until the mock refuses.

The specifications settle less of this than they look like they do. RFC 6750
fixes the two error codes and the status each answers with, and NRPS 2.0 fixes
the scope string; **which services enforce, and when**, is a property of a
platform, and this one is a fake platform whose whole job is to be built
against. That is the contestable half, and it is what this record decides. The
grant itself is [ADR 0084](0084-the-mock-platforms-token-endpoint-bounds-an-assertion-at-five-minutes.md)'s.

## Decision

**NRPS enforces now.** `GET` on a context's memberships URL requires
`Authorization: Bearer <token>` where the token is one this platform's own token
endpoint issued, carrying NRPS 2.0's membership scope. A missing or malformed
header is `401` with a bare `WWW-Authenticate: Bearer` challenge and no error
code (RFC 6750 §3.1: there is no credential to have got wrong); a token this
platform did not sign, or one whose `exp` has passed, is `401` with
`error="invalid_token"`; a token it issued for some other scope is `403` with
`error="insufficient_scope"` and the scope required. The codes ride the
challenge because RFC 6750 §3 is the only document that defines them and that is
where it puts them.

**AGS does not enforce, and the reason is E1-06's argument still standing.**
SPEC §3.4 states the passback rule and SPEC §14.3 gives the work to **E3 — Grade
passback**, so no AGS client exists yet and a `401` there would be refused by
nothing but this repository's own E0-15 tests — `docs/MISTAKES.md` entry 22
exactly, and with no client to prove conformance against, the refusal would
assert nothing. **Owner: E3, which builds the first AGS client**, recorded with a
"done when" in [`docs/tickets/e1/deferred.md`](../tickets/e1/deferred.md).

**The check lives beside the mint.** `app.tokens::authorised_token` is the one
door, and it is in the module that issues tokens rather than in `app.nrps`,
because reading a token back is `issued_token`'s rules read in reverse — same
issuer, same audience, same key, same clock. Which scope opens which service
stays with the service: the route names `MEMBERSHIP_SCOPE` and the door asks no
questions about what it means. The credential is checked before the query
parameters and before the context lookup, so an unauthenticated caller learns
neither which contexts are seeded nor which filters exist.

## Alternatives rejected

- **Enforce on AGS in the same change, for symmetry** (E3's work, done early).
  It would turn every
  E0-15 line-item, score and result test red for a reason none of them is about,
  and buy a refusal no client has ever asked for. Symmetry between two services
  at different stages of their life is not a property worth paying a suite for.
- **Leave NRPS open until E3 as well, and prove the exit clause another way.**
  There is no other way: the clause distinguishes an authenticated read from an
  unauthenticated one, and only the platform can tell them apart.
- **A store of issued tokens, checked by lookup.** A mock with a store behaves
  differently after a restart, which is the thing this platform exists not to
  do. E1-06 minted a signed JWS precisely so a service could check one with
  nothing remembered; a store here would make that argument false in the same
  change that first depended on it.
- **Put the error code in a JSON body.** A client that reads RFC 6750 reads the
  challenge, and a platform that stated the code only in a body would teach the
  tool built against it to look in the wrong place.
- **State an `error_description` in the challenge.** RFC 6750's ABNF excludes
  the double quote and the backslash from that parameter, so it is the one place
  a caller's own bytes could rewrite the challenge's syntax. The description
  goes in the response body, which has no such constraint.
- **A configuration flag for whether the services enforce.** Two behaviours to
  test, one of which is the one nobody wants, and a knob a green run could be
  hiding behind.

## Consequences

- A test driving the mock's roster by hand must obtain a token first. The two
  suites that did not — the raw-transport controls in
  `test_the_roster_sync_is_a_conformant_service_client.py` — are red on this
  branch and disputed rather than worked around
  ([`docs/disputes/E1-11-06.md`](../disputes/E1-11-06.md)); a conformant client
  is unaffected, because `pylti1p3` obtains a token before every service call.
- The mock now has two service surfaces with two different rules, which is a
  thing to state rather than a thing to notice. `mock-lms/app/main.py`'s
  Advantage comment says which is which and who owns the other half.
- Enforcement reads this process's own key, so it verifies exactly what it
  minted. Two platforms started in one process hold two keys, and a token from
  one is refused by the other — which is a real platform's behaviour and is now
  observable here.
- The roster costs an RSA verification per request. The handler is synchronous,
  so FastAPI already runs it off the event loop, and the seed is a development
  stack.
- **The AGS owner is E3 and several places in the repository say E2.** This
  ticket's own work order, the mock-platform test driver and three test module
  docstrings all read "grade passback is E2 (SPEC §3.4)". §3.4 is the section
  that states the passback rule; SPEC §14.3 names **E3 — Grade passback** as the
  epic that builds it, and E2 is the weekly survey. The records this change owns
  say E3; the test-side prose is the test author's to correct, and is noted in
  the pull request rather than edited here.
