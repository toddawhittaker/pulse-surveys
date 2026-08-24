# 0062 — A request is parsed once, at the edge, and nothing downstream re-derives it

**Status:** Accepted
**Date:** 2026-08-18
**Tickets:** E0-16; re-verified and amended by E0-30

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
   decodes twice or coerces. `app.flow.carried()` judges *presence* on a trimmed
   copy and hands the untrimmed value on, because "three spaces is not a `state`"
   is a different statement from "your `state` is these three spaces". It is one
   function rather than the same test written wherever an answer is wanted:
   `required()` refuses the request on its verdict and the error redirect decides
   whether to echo `state` on the same one, so the two cannot disagree about
   whether a parameter arrived.
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
   whose query already carries a name a response appends. That set is
   `app.config.RESPONSE_PARAMETERS`, and it is a set rather than a pair because
   E0-30 gave the provider a second response to send to the same address: `code`
   and `state` on a grant, `error` and `error_description` on a refusal.

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

**One of those strictnesses is worth naming, because it reads as a bug.**
`openid␠␠email` — an empty token between two valid ones — is refused, and so is
any other doubled space in a scope: RFC 6749 Appendix A.4 makes a scope token
`1*NQCHAR`, and the empty string between two spaces is not one. Some real
servers tolerate it. **E0-30 affirmed the strictness rather than fixing it**, and
the reasoning is the paragraph above read in one direction only: a client that
satisfies this provider satisfies every real one, while a mock that accepts what
a real platform will not is E0-28's whole subject. So the next person who meets
a refused double space has met a decision, not a defect.

**A parse that is wrong is wrong in one place.** That is the trade for the
strictness: `SCOPE_TOKEN` and `PKCE_ALPHABET` are each read by exactly one check,
and a mistake in either is one line rather than a divergence between two call
sites.

**It says nothing about the tool side.** E1 writes the client, where the same
question arrives mirrored — what a client may normalise in what a provider sent
it — and the answer there is not obviously this one. What does carry over is the
rule about echo semantics: a value the protocol requires back unchanged is
untouchable in both directions.

**The transport of a refusal is settled now, and it was not settled here.** When
this record was written the provider answered every refusal with a page and the
error redirect was deferred, which this record noted and did not decide.
[E0-30](../tickets/e0/E0-30-review-debt-from-e0-16.md) decided it: a refusal
raised after `client_id` and `redirect_uri` have validated is delivered to the
registered redirect URI as RFC 6749 §4.1.2.1 requires, carrying `error`,
`error_description` and the `state` that arrived, and the refusals raised before
that point stay pages because there is no address the provider has established
the right to use. Two things there are this record's rule pointing outward:
`state` is echoed exactly as it arrived on the error path as well as the success
one, and `app.flow.added_to_query` is the single place the parameters are added
to the registered URI's query rather than substituted for it — one rule, so the
two responses cannot come to disagree about a registration that carries a query
of its own.

**E0-30's own security review then found the first rule broken inside the change
that implements that decision**, which is worth recording rather than quietly
fixing, because it is the clearest instance of the defect this record is about. A
request whose `state` was three spaces was refused *for carrying no `state`* and
the refusal came back carrying `state=%20%20%20`: the presence verdict was taken
by `required()` on the way in and then **re-derived** at the redirect as
`state or None`, which asks Python whether the string is truthy and gets the
opposite answer. One request, two incompatible answers to "did a `state`
arrive", and the client can only see the wrong one. The verdict is
`app.flow.carried()`'s now, and the redirect reads it rather than taking it
again.

**The same round bounded `error_description`, and that is this record's rule
turned the other way round.** Every refusal quotes the parameter that was wrong,
so a caller who sends `response_type=token"\<script>…§` chooses the bytes the
client receives — a `"` or a `\` ends a quoted string early in whatever reads the
redirect next. A value is not repaired on the way *in*, by rule 1, so it has to
be bounded on the way *out*: `app.flow.bounded_to_nqschar` maps the description
onto RFC 6749 Appendix A.8's `1*NQSCHAR` at `error_response`, the single place
the redirect's parameters are built, rather than at each raise site — a bound
that has to be remembered at every `raise` is one that will be forgotten at the
next. The refusal *pages* keep their prose exactly as raised: a page is escaped
and read by a person, and the grammar is a property of the protocol field, not of
the sentence.

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

**The three limits were re-verified after E0-30**, which edited both swept
modules and is the first change to them since the gate was written. The swept
set is still those six names: the error redirect introduced no normalisation at
all — it is built from `urlsplit`, `quote` and `urlunsplit` — so nothing was
measured that would justify widening it. The four permitted shapes still cover
every call the sweep finds, and each still covers something: eleven calls, being
three configuration reads in `config.py`, four presence tests, the scope split
against RFC 6749 Appendix A.4's delimiter, and the three that normalise a media
type off one request header. The other two limits are properties of how the gate
is written rather than of the tree, and neither changed.

**Re-verified again after E0-30's second fix round, which added one
transformation and moved another.** `bounded_to_nqschar` is new, and it is not a
normalisation of request data: it maps the provider's *own* description onto a
character set on the way out, nothing compares its result with anything a client
kept, and `state` goes back untouched beside it. It is written as a comprehension
over a frozenset rather than as a call to any swept name — which also makes it an
example of the second limit, since the gate would not see it whichever way it
were spelled. The presence test that was in `required()` is now in `carried()`,
one function further down the same call, so the sweep still finds eleven calls
with the same permissions and the swept set is still six names.

So the rule is enforced against the mechanism that produced all five defects, and
a sixth arriving by another route is still caught by review or by nothing.
