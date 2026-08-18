# 0056 — Only a timeout fails open, and a credentialled endpoint must be encrypted

**Status:** Accepted
**Date:** 2026-08-18
**Tickets:** E0-13

## Context

SPEC §3.3 sanctions exactly one fail-open in this codebase:

> Classifier latency budget: p95 < 2s; on provider timeout, the heuristic floor
> applies and the submission is accepted, then classified async (fail open, never
> block a student on an outage).

E0-13's first implementation read "provider timeout" broadly. The gateway had one
class, `AIProviderUnavailableError`, covering every failure that was not an HTTP
status — a read timeout, a refused connection, a DNS failure, a TLS handshake that
did not complete — and the validity task fell open on all of them.

E0-13's review measured what that means. Pointing `AI_PROVIDER_BASE_URL` at an
`https://` endpoint whose handshake fails produced the message "The model endpoint
did not answer within the task's timeout" and applied the character floor. A
certificate that does not validate is what an active network attacker looks like,
and §10 makes transport encryption mandatory rather than optional.

The same review found the configuration side of it: `ai_provider_base_url` is a
bare string with no scheme check, so `http://` with a credential configured sends
the bearer token *and* the student's comment in cleartext, and nothing in the
system objects.

## Decision

**A timeout is its own failure class, and it is the only one the validity task
falls open on.** `AIProviderTimeoutError` means the endpoint accepted the request
and did not answer in time. `AIProviderUnreachableError` means the request never
arrived — a refused connection, a name that did not resolve, a handshake that did
not complete. `app.ai.tasks` catches the first and lets the second propagate.

**The two are told apart by the exception chain, not by a message.** The layers
above flatten both into one class carrying a sentence — "Request timed out."
against "Connection error." — and a rule that reads either sentence breaks when
the library rewords it. `_timed_out` walks `__cause__`/`__context__` looking for
`httpx.TimeoutException`, the common parent of a connect timeout and a read
timeout, and the deepest layer this project declares a dependency on. Measured on
the pinned versions: a stub holding the request yields `ModelAPIError <-
APITimeoutError <- httpx.ReadTimeout`; a refused connection and a failed TLS
handshake both yield `ModelAPIError <- APIConnectionError <- httpx.ConnectError`,
with no `TimeoutException` in either. **A chain the check cannot read answers
`False`**, so an unrecognised failure is surfaced rather than absorbed.

**`AI_PROVIDER_BASE_URL` must be `https`, or name this machine, whenever
`AI_PROVIDER_API_KEY` is set.** Refused at startup by a validator on `Settings`,
with no value quoted, so a misconfiguration stops the container rather than
leaking on every submission.

## Alternatives rejected

**Keep one class and fail open on all of it.** The reading that "never block a
student on an outage" covers every way a request can fail. Rejected because it
hands the decision to whoever can interrupt the connection: an attacker who can
force a handshake failure can force *no classification*, indefinitely, and the
submission is accepted anyway. That is tolerable for a participation gate and not
for §6.2's moderation path, which E2 puts through this same gateway — and a rule
that has to be tightened later, on the safety path, is a rule that will be
tightened after the first incident rather than before it.

**Fail open on a refused connection but not on TLS.** The nearest thing to §3.3's
intent: a provider container that is down is an outage in the ordinary sense, and
blocking every student on it is exactly what §3.3 says not to do. Rejected as a
distinction this code cannot draw honestly — a refused connection and a failed
handshake arrive identically shaped, and telling them apart means reading the
`ssl` module's exception types out of somebody else's chain. **The consequence is
named rather than hidden**: with the provider unreachable, every submission now
raises instead of being accepted by the floor, and E2's submit path is where that
is caught and answered. E2 must decide it deliberately; today nothing but a test
calls this code.

**Classify on the exception's message.** One line instead of a chain walk, and
wrong for the reason above: the message is the library's to reword, and the
project pins that library precisely because it moves.

**Require `https` unconditionally.** Stricter and simpler, and it breaks a real
deployment: a model server inside a private network, reached over `http://` with
no credential — the vLLM-in-a-cluster case `.env.example` and `README.md` both
document. Rejected in favour of the narrower rule, which leaves that case working.

**Check the scheme in the gateway rather than in `Settings`.** It would catch the
same thing one layer later, at the first classification rather than at startup,
which is the difference between a container that will not start and a container
that serves for a week and then leaks on the first comment.

## Consequences

**Cleartext to an off-machine endpoint with no credential is still permitted**,
and that is a hole this record names rather than closes. Student comment text
would cross a network unencrypted; whether the network is private enough for that
is the operator's judgement, and §10's requirement then rests on them rather than
on the configuration surface. Closing it means refusing `http://` to anything but
this machine, which is a deployment policy decision and Todd's to make.

**A provider outage now blocks the validity call rather than floors it**, unless
the outage takes the shape of a timeout. In practice a down endpoint usually
refuses the connection immediately, so this is the common case and not an exotic
one. E2 owns the submit path and has to answer for it — accepting the submission
on `AIGatewayError` generally, or on `AIProviderUnreachableError` specifically,
is a decision with a student on the other end of it, and it is not E0-13's to
make on E2's behalf.

**A `Settings` validator's own message does not reach the operator.**
`_describe_invalid_settings` builds its report from the field name, the field's
static `description=` and pydantic's error-type code, so a `value_error` renders
as "rejected by this setting's own validation". The transport rule is therefore
written into the field's `description`, where it is printed. That is a
readability limitation of `app/config.py` rather than of this decision, and
widening the report to include validator messages would mean trusting every
future validator not to quote its input — which is the sort of convention
`docs/MISTAKES.md` entry 2 exists to distrust.
