# 0062 — A request is parsed once, at the edge, and nothing downstream re-derives it

**Status:** Accepted
**Date:** 2026-08-18
**Tickets:** E0-16

## Context

Three review rounds against the mock OIDC provider found six defects, and five of
them are one shape: **a value was transformed between the wire and the check that
was supposed to judge it.**

- Every parameter was read through a helper ending in `.strip()`, so the PKCE
  shape check could not see whitespace. For a challenge registered over verifier
  `v`, every string trimming to `v` was accepted — PKCE bound a set instead of a
  string — and `state` and `nonce` came back trimmed, against RFC 6749 §4.1.2 and
  OIDC Core §3.1.3.7.
- The scope was split with a bare `str.split()`, which treats a tab, a newline
  and U+00A0 as separators. RFC 6749 Appendix A.4 separates scope tokens by one
  space and by nothing else, so `openid\temail` — one unknown token to a
  conformant server — arrived as two known ones, and the unknown-scope refusal
  added the round before could not fire.
- The duplicate-parameter rule ran over one collection at a time, so a name sent
  once in the query and once in the body was two singletons rather than one
  duplicate.
- The registered redirect URI was checked with `urlsplit(...).fragment`, whose
  empty-string result for a trailing `#` is falsy.
- The granted scope was stored as a string and re-split where it was used.

Each fix was local. What none of them addressed is why the same shape kept
arriving: nothing said where parsing happens, so it happened wherever a value was
needed, with whichever tool was nearest.

[SPEC §9.2](../SPEC.md) asks for a standards-compliant provider and says nothing
about how it reads a request, and a reasonable engineer might reach for
normalise-then-validate — it is what most web code does, and it is defensible
when the thing being parsed has no wire grammar to be wrong about.

## Decision

**One parse, at the edge, into typed values; every check and every echo reads
what that parse produced or what actually arrived.** Concretely, in
`mock-idp/app/`:

1. **Values are read exactly** (`app.flow.submitted`). Nothing trims, lowercases,
   decodes twice or coerces. `required()` judges *presence* on a trimmed copy and
   hands the untrimmed value on, because "three spaces is not a `state`" is a
   different statement from "your `state` is these three spaces".
2. **Grammar checks use the specification's grammar**, written out where it is
   used: `SCOPE_TOKEN` for RFC 6749 Appendix A.4, `PKCE_ALPHABET` for RFC 7636
   §4.1. A standard-library parser named after a thing is not a check against it.
3. **Whole-request questions are asked before a mapping exists.**
   `repeated_parameters` runs over the query and body pairs together, because
   `dict()` is where a repetition stops being visible and because RFC 6749 §3.1
   is a statement about the request rather than about one encoding of it.
4. **Parsed is kept parsed.** The granted scope travels as `tuple[str, ...]` on
   the pending request and on the authorization code, never as a string to be
   split again. A second parse is a second grammar to keep in step with the
   first.
5. **Configuration is checked against the shape it will be used in.**
   `ProviderSettings.validate` refuses a redirect URI carrying a fragment — by
   looking for `#` in the string, not for a truthy `urlsplit` component — and one
   whose query already carries `code` or `state`, because the authorization
   response appends exactly those.

## Alternatives rejected

**Normalise at the edge, then validate the normalised value.** The conventional
shape, and the one this code had. It is right where normalisation is part of the
contract — a case-insensitive header, a percent-decoded path — and wrong for
every value here, because each one is either compared byte for byte with
something the client kept, hashed, or echoed back under the client's name. Five
defects came out of it in three rounds.

**Validate at the edge and re-parse where convenient.** Cheaper to write and it
is how the scope string became two grammars. The second parse is invisible at the
first one's site, so nothing about the first check tells a reader it can be
undone later.

**A schema library at the boundary** — Pydantic models for the request shapes.
It would centralise the parse and it changes what the boundary *does*: a model
coerces, fills defaults and drops unknown members, which is the same class of
repair this record exists to keep out. It also cannot express "this name must not
appear twice", because it takes a mapping.

**Say nothing and rely on review.** Three rounds is the measurement of how well
that works: each round found the shape in a place the previous round had not
looked, and the second round's fix (hardening the PKCE guard) sat downstream of
the repair that made it unable to fire.

## Consequences

**Refusals are stricter than a lenient client expects, and that is the point.**
A doubled space in a scope, a trailing newline on a verifier, a duplicated
parameter and a fragment on a redirect URI are all refused here and by Keycloak,
Okta, Azure AD or Auth0 — and were all accepted by this provider a round ago. A
tool built against a mock that shrugs learns to shrug (E0-16's definition of
done, and the subject of
[E0-28](../tickets/e0/E0-28-review-debt-from-e0-15.md) on the platform side).

**A parse that is wrong is wrong in one place.** That is the trade for the
strictness: `SCOPE_TOKEN` and `PKCE_ALPHABET` are each read by exactly one check,
and a mistake in either is one line rather than a divergence between two call
sites.

**It says nothing about the tool side.** E1 writes the client, where the same
question arrives mirrored — what a client may normalise in what a provider sent
it — and the answer there is not obviously this one. What does carry over is the
rule about echo semantics: a value the protocol requires back unchanged is
untouchable in both directions.

**One thing this does not cover, stated so it is not read as covered.** The
provider still answers refusals with a page rather than RFC 6749 §4.1.2.1's
redirect carrying an `error` — deferred, and Todd's call — and this record does
not decide it.

**A gate enforces the first rule, and its limits are part of what it enforces.**
`tests/unit/test_the_provider_judges_the_value_that_arrived.py` sweeps every call
to `strip`, `lower`, `upper`, `casefold`, `split` or `unquote` under
`mock-idp/app/` by parsing the source, and requires each to match one of four
permitted **shapes**: a configuration read in `config.py`, a presence test whose
result is discarded (`if not value.strip():` and only that — `if value.strip() ==
expected:` is the defect wearing the same clothes), a `split` with an explicit
delimiter, or a media type normalised off a request header. Shapes rather than
line numbers or counts, so a fifth presence check added next month passes by
having the property rather than by anybody re-counting.

Three limits travel with it, and an ADR claiming a gate covers more than it does
is worse than one admitting it covers nothing:

- **The swept set is six names, and it is six because six were measured against
  this tree.** `rstrip`, `lstrip`, `replace` and every other way to change a
  value are not swept. Widening the set without measuring it would make the gate
  fail on ground nobody has looked at, and a gate that fails for an unmeasured
  reason teaches people to add exclusions.
- **It is syntactic, not dataflow.** It sees the shape of a call, never where the
  value came from. A normalisation of request data written in one of the four
  shapes passes — which is the point for three of them, and for the
  configuration shape rests on `config.py` staying a configuration module.
- **It reads the source rather than the running application**, so a
  normalisation reached through `getattr` or inside a library call is invisible
  to it.

So the rule is enforced against the mechanism that produced all five defects, and
a sixth arriving by another route is still caught by review or by nothing.
