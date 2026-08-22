# 0056 — What fails open, what raises, and what the provider URL may carry

**Status:** Accepted. Rewritten after E0-13's second review pass measured two of
its rows wrong; the decision that the fail-open is narrower than "any failure"
stands, and where the line sits has moved. Amended 2026-08-21 (E0-37): item 12
closed the keyless-cleartext allowance this record used to name, and item 13
recorded why HTTP 429 and 500 sit outside the floor. The taxonomy is unchanged.
**Date:** 2026-08-18
**Tickets:** E0-13, E0-37

## Context

SPEC §3.3 sanctions exactly one fail-open in this codebase:

> Classifier latency budget: p95 < 2s; on provider timeout, the heuristic floor
> applies and the submission is accepted, then classified async (fail open, never
> block a student on an outage).

E0-13's gateway first read that broadly: one class covered every failure that was
not an HTTP status, and the validity task fell open on all of it — including a TLS
handshake that did not complete, which is what an active network attacker looks
like.

The first correction split "timeout" from "unreachable" and said only a timeout
floors. **The second review pass measured that the split did not hold at either
end.** `httpx.ConnectTimeout` is a subclass of `httpx.TimeoutException`, so a chain
walk looking for the parent matched it: against a blackholed route the classifier
floored with **zero requests reaching any server**, while the class's own
docstring said "the endpoint accepted the request". Dropping packets is cheaper
than forcing a TLS failure and had the same effect — which is the argument the
first version of this record used *against* flooring on TLS. At the other end, an
HTTP 503 — a load balancer answering while the model behind it is down, the
ordinary shape of a hosted outage — raised, blocking every student on precisely
the case §3.3's sentence was written for.

Separately, the transport rule this record introduced asked whether
`AI_PROVIDER_API_KEY` was set. A credential in the URL's userinfo made it answer
"no": `http://user:password@provider.example.com/v1` was accepted, and the client
turned the userinfo into a real `Authorization: Basic` header. The password also
appeared in `repr(settings)` and `model_dump()`, because the field is a plain
`str` — beside `database_url`, which is masked, and inside the object §6.3's admin
configuration view renders.

## Decision

**The line is whether the request reached an endpoint that could have answered,
and then whether what came back was about the endpoint or about the request.**

| What happened | Class | Floors? |
|---|---|---|
| Read timeout — connection open, request sent, no answer in time | `AIProviderUnavailableError` | **yes** |
| Write timeout — connection open, request stalled going out | `AIProviderUnavailableError` | **yes** |
| HTTP 408, 502, 503, 504 — the endpoint says it cannot serve now | `AIProviderUnavailableError` | **yes** |
| Connect timeout — packets went into a hole, nothing arrived | `AIProviderUnreachableError` | no |
| Connection refused, DNS failure, TLS handshake failure | `AIProviderUnreachableError` | no |
| Connection reset or dropped mid-stream | `AIProviderUnreachableError` | no |
| Pool timeout — the request never left this process | `AIProviderUnreachableError` | no |
| HTTP 401, 403, 404, 429, 500, or any other status | `AIProviderRefusedError` | no |
| An answer that is not the contract, twice — including a 200 that is not JSON | `AIResponseInvalidError` | no |

Three rules produce that table, and they are worth stating apart from it:

**Reached, and did not classify → the floor.** That is §3.3's sentence: the
provider was there and no verdict came back. A read or write timeout and an
availability status are the same event seen at two layers, and a student should
not be blocked by either.

**Never arrived → raise.** Nothing got as far as an endpoint that could have
answered, so "the provider is having an outage" is one explanation among several,
and the others are a typo in the base URL, a network that is down, and somebody on
the path. A connect timeout is in this group *because* it is the cheapest thing an
attacker can force: if it floored, anyone able to drop packets could decide that no
classification happens.

**Answered about the request → raise.** A rejected credential, a rate limit, a
model that does not exist, a schema the endpoint will not accept. None of these
resolves on its own, and flooring on them would hide a permanent misconfiguration
one comment at a time.

**Why 429 and 500 in particular are outside the floor**, since they are the two
rows in that group a reader is most likely to argue with — E0-13's implementer
named them as the ones expecting an argument, and Todd affirmed them as built on
2026-08-18. They are both cases where the endpoint answered, so the classifier
knows the provider is there; what it also knows is that the answer was about our
own request. **A 429 is a capacity decision an operator has to see**: the account
is over its limit, and flooring turns a bill or a plan that needs changing into
silently degraded classification that nobody is told about. E2's queue owns the
backoff, so absorbing it here would take the decision away from the layer that
can act on it. **A 500 means our request is the problem** far more often than it
means the provider is having an outage — a payload the model cannot parse
returns exactly this — and the outage shape has its own statuses in the floor
above. Flooring on either hides a condition that never resolves on its own, one
comment at a time, for as long as it takes somebody to notice that no comment has
been classified since Tuesday. The cost of raising is the opposite and much
louder: E2 sees the error on the submit path and answers for it.

**The classification is made on the exception chain, never on a message.** The
library flattens all of these into one class carrying a sentence — "Request timed
out." against "Connection error." — and a rule that reads either breaks when the
library rewords it. `_unanswered_outcome` looks for `httpx.ReadTimeout` and
`httpx.WriteTimeout` *specifically* rather than for their common parent, which is
the mistake this revision corrects. **A chain the check cannot read is treated as
unreachable**, so an unrecognised failure surfaces rather than being absorbed.

**`AI_PROVIDER_BASE_URL` carries no credential of its own**, and is refused at
startup if it does — over https as well as http, and on loopback as well as off
it, because the problem is not only the wire. And the URL must be `https` unless
it names this machine.

> **Amended 2026-08-21 (E0-37 item 12).** That last sentence used to read "when
> `AI_PROVIDER_API_KEY` *is* set, the URL must be `https` or name this machine",
> and the validator returned early when no key was configured. Todd decided on
> 2026-08-18 that off this machine means `https` with or without a credential:
> the key is not the only secret on that connection, and the student comment in
> the body of every request is the one SPEC §4 and §10 protect. The rule no
> longer reads `AI_PROVIDER_API_KEY` at all.

## Alternatives rejected

**One class for every failure, flooring on all of it.** The original state.
Rejected because it hands the decision to whoever can interrupt a connection, and
because it made "the provider is unreachable" indistinguishable from "the provider
is slow" in the stored record.

**Flooring on any `httpx.TimeoutException`.** The first correction, and wrong for
the reason above: the parent class contains the two cases where nothing arrived.
The lesson generalises — matching on a base class is a decision about every
subclass, including the ones added after you write it.

**Flooring on every 5xx.** Simpler than a set, and it puts `500` in the floor —
the status a provider returns when *our* request is the problem, so a schema it
cannot parse would degrade every classification to the character floor silently
and permanently. `429` is excluded for the same shape of reason: a rate limit is a
capacity decision an operator has to see, and E2's queue owns the backoff.

**Refusing to floor on a status at all**, keeping the floor to transport-level
timeouts. Tidy, and it fails the case §3.3 is most likely to meet: hosted providers
report outages with status codes, not with hanging sockets.

**Masking `ai_provider_base_url` as a `SecretStr`** so a userinfo password cannot
leak through `model_dump()`. Rejected because §6.3 specifies an admin view showing
"AI provider (base URL, model, masked key)" — the base URL is meant to be
*visible*, and masking it to defend against a credential that should not be there
solves the wrong half. Refusing the credential keeps the field displayable, which
is what §6.3 asks for. (It also used to make the transport rule's question — "is
a credential configured?" — answerable from one place; since E0-37 item 12 that
rule asks no such question, so this alternative loses one of its two reasons and
keeps the one the spec gives.)

**Asking whether a credential is configured *anywhere*, including the URL, and
then requiring TLS.** The narrower fix, and it leaves the password in
`repr(settings)` and in the admin view. Refusing it outright closes both at once.

## Consequences

**Cleartext to an off-machine endpoint with no credential was permitted, and is
not any more.** This record used to name that hole rather than close it: student
comment text would cross a network unencrypted, and whether the network was
private enough for that was called the operator's judgement. **E0-37 item 12
closed it on 2026-08-21**, to a decision Todd made on 2026-08-18 — the comment is
in the body of every request whether or not a credential is configured, §10 does
not allow it on the wire in the clear, and a deployment that wants a model in its
own cluster terminates TLS at the model or runs it alongside the application.
Nothing here still offers the keyless-cleartext case, and nothing in this record
argues for it: the paragraph that did, in `app/config.py`'s validator docstring,
cited this ADR and went with the same change.

**A provider that is unreachable blocks the validity call.** With the availability
statuses moved into the floor this is the narrower case it was meant to be — a
hosted provider having an outage usually answers 502 or 503 — but a self-hosted
endpoint that is simply down still refuses connections, and every submission then
raises. E2 owns the submit path and has to answer for it deliberately: catching
`AIGatewayError` there is a decision with a student on the other end of it, and it
is not E0-13's to make on E2's behalf.

**The four classes are the interface E2 branches on**, and they are named for the
decision rather than for the mechanism. `AIProviderUnavailableError` means "the
floor applies"; the other three mean "do not floor". A case added later belongs in
the table above in the same change that adds it.

**A `Settings` validator's own message does not reach the operator.**
`_describe_invalid_settings` builds its report from the field name, the field's
static `description=` and pydantic's error-type code, so a `value_error` renders
as "rejected by this setting's own validation". Both configuration rules above are
therefore written into the field's `description`, where they are printed. That is
a readability limitation of `app/config.py` rather than of this decision, and
widening the report to include validator messages would mean trusting every future
validator not to quote its input — the sort of convention `docs/MISTAKES.md` entry
2 exists to distrust.
