# 0106 — A launch that names nobody is refused, against LTI 1.3's MUST

## Context

LTI 1.3 Core §5.3.6.1 is explicit: a tool "MUST interpret the lack of a `sub`
claim as an anonymous user". So an `id_token` with every other claim in order
and no `sub` is a **conformant** message that a certified platform may send,
and a certified tool is required to have an answer for it.

Pulse has no anonymous user. Every view in SPEC §4 is somebody's, scoped to the
person who opened it; the launch door resolves the subject to a `user` row
(ADR 0045's sanctioned writer) and E1-12 resolves that row to a person before
any landing is chosen. There is no screen in this product that can be shown to
a caller with no identity, and no record it could be written against.

What that cost until now was measured by the E1 boundary review (finding M4).
Such a launch passed every guard in `app.lti.launch`, **spent its nonce**, and
then raised `UnregisteredLaunchError` inside
`app.services.provisioning._record_the_launching_subject`, which reads the
claim and had nowhere to put its absence. The door answered HTTP 500 with a
traceback, to an unauthenticated caller, on a message the specification calls
well formed — and the spent nonce meant the retry was refused too.

## Decision

**A launch carrying no `sub` is refused, and Pulse breaks the MUST
deliberately.** `AnonymousLaunchRefused` joins the `LaunchRefusedError`
subclasses in `app.lti.launch` and fires as the last check in `_validate`,
after the version check and before the nonce is spent. Everything else follows
from being one of that family and nothing is special-cased: the calm shared
refusal page, HTTP 400, `data-reason="AnonymousLaunchRefused"` (ADR 0103), one
`WARNING` on `app.lti.launch` carrying the guard name and nothing else, the
in-flight handshake consumed exactly as every other refusal consumes it, and no
session issued.

Refusing politely is the honest answer to a message this product cannot serve.
Admitting an anonymous launch would mean showing somebody a page built for a
person Pulse cannot name, which is a worse lie than saying no.

## Alternatives rejected

- **Support anonymous launches, as the specification requires.** It would mean
  building a view for a person the product has no representation of — no
  assignments, no enrollment, no purview, nothing §4 can scope. Every screen
  would need a second, identity-free shape, and every read path a second answer
  to "whose data is this", which is exactly the question SPEC §8's identity
  separation exists to make unambiguous. A conformance box ticked by a page
  that shows nobody anything is not conformance worth having.
- **Leave the crash.** It is what the boundary review measured: a conformant
  message answered with a 500 after spending its nonce, so the platform's
  legitimate retry is refused as a replay and the operator sees a traceback
  rather than a refusal. A 500 is also the one answer that tells a caller
  nothing about what to fix.
- **Refuse it inside `app.services.provisioning` instead**, where the claim is
  already read. The nonce is spent by then and the handshake consumed on a
  different path, so the refusal would not have the shape every other refusal
  has — and the service would be deciding admission, which is the door's job
  (SPEC §13's split, and the one authorization chokepoint rule).
- **Substitute a synthetic subject** — a per-launch identifier standing in for
  the missing one. It would write a `user` row per anonymous launch, growing
  without bound, each one an identity nothing can ever link, resolve or merge.
  `b8c41f7d2e05`'s `pre-binding-section-` backfill is the same idea applied to
  sections, and the H2 finding in the same review is what that costs.

## Consequences

- **Pulse is not conformant with LTI 1.3 Core §5.3.6.1, knowingly.** If
  certification is ever pursued this is the row that fails, and this record is
  the answer to give. Nothing else in the launch door departs from the
  specification.
- A platform configured to launch anonymously — a public course, a preview link
  — gets a calm page saying so rather than an error, on every launch. That is
  visible to the platform's administrator as a refusal with a name, in the
  browser and in the log, which the 500 was not.
- `_record_the_launching_subject`'s own refusal for an absent `sub` stays where
  it is. Its message already said the door "has already required" the claim;
  that statement is true from this change on, and the raise remains as defence
  in depth for any future caller that reaches the writer another way.
- The guard vocabulary the doors publish grows from ten launch names to eleven.
  ADR 0103, its index row, and the door suites' guard lists count them.
