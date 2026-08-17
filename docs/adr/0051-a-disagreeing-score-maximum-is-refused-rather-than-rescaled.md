# 0051 — A disagreeing `scoreMaximum` is refused rather than rescaled

## Context

E0-15 rules that the mock platform's AGS Results endpoint does not rescale:
`resultScore` is the posted `scoreGiven` and `resultMaximum` is the line item's
own maximum. That ruling is in the ticket and is not reopened here.

AGS 2.0 does not require the two maxima to agree. A tool may post `scoreGiven`
8 out of `scoreMaximum` 10 against a line item whose maximum is 100, and the
specification expects the platform to scale the score into the line item's
range — Canvas reads that as 80. The review round found the mock taking the
mismatch and dropping it: the score was accepted, and the `Result` read back
`resultScore` 8 out of `resultMaximum` 100.

So the no-rescale ruling and AGS's permissiveness produce a wrong grade
together. Neither is wrong on its own, and the combination is silent — the post
answers 200, the container answers a well-formed `Result`, and both ends look
correct. SPEC §3.4 always posts a percentage into a line item whose maximum
defaults to 100, so the exposure in this product is narrow; the exposure to E3
being *written against this behaviour* is not.

## Decision

A score whose `scoreMaximum` differs from the line item's own maximum is
refused, with a 422 naming both numbers. It is refused whether or not
`scoreGiven` is present, and a `scoreGiven` with no `scoreMaximum` at all is
refused separately, because a score is a fraction and half of one is no fact.

**This is a deliberate narrowing of AGS 2.0 rather than conformance to it, and
the mock is the wrong place for a narrowing to be invisible.** The rule is stated
in the ticket, asserted by a test whose docstring marks it as going past the
specification, and recorded here.

**What E3 has to learn from it: post against the line item's own maximum, and
never rely on a platform to scale.** A tool that reads the line item it created,
posts out of that maximum, and treats a disagreement as its own bug is correct
against this mock, against Canvas, and against a platform that refuses the
mismatch outright. A tool that posts out of 10 and expects scaling is correct
against Canvas alone.

## Alternatives rejected

**Rescale, as Canvas does.** The conformant choice, and it contradicts the
ticket's ruling that Results does not rescale. Taking it would mean reopening
that ruling, and the ruling is right for the reason it was made: a mock that
rescales makes every E3 assertion about a posted number a question about
arithmetic nobody wrote down, and a test that expects 61.5 and reads 61.5 cannot
tell "no scaling happened" from "scaling happened and was the identity".

**Accept the mismatch and keep dropping it, as the mock did.** This is the state
the review found and it is the worst of the three: it is neither conformant nor
loud. The grade that comes back is a different grade from the one posted, and
nothing anywhere says so.

**Accept it and rescale only where the maxima disagree.** A hybrid that is
conformant *and* keeps the equal case exact. Rejected because it makes the
platform's behaviour depend on a coincidence — the same posted `scoreGiven` means
one grade when the maxima match and another when they do not — and because the
rescaling path would then be code no test in this repository exercises, since
§3.4 never posts a disagreeing maximum. Untested arithmetic on a grade is the
thing this record exists to avoid.

**Leave it to a `PlatformProfile` adapter in E1.** The adapter layer is where
per-platform deviations belong (§7.3), and this is not a deviation the mock is
imitating — it is the mock's own rule. An adapter for the reference platform
would also be the first quirk profile written against something that is not a
real LMS.

## Consequences

**The mock is stricter than the specification here, and that is a cost as well
as a guarantee.** A tool written against this platform and then run against
Canvas will find Canvas *more* permissive, which is the safe direction: code that
passes here passes there. The unsafe direction — permissive mock, strict
platform — is what the other three refusals in this round closed, and this one
is deliberately not symmetric with them.

**A test that wants to exercise scaling has nowhere to do it.** Nothing in E0 or
E3 needs one, because §3.4 posts a percentage of the line item's maximum by
construction. If a later epic needs to prove its handling of a scaling platform,
that is a `PlatformProfile` fixture rather than a change here, and this record is
where the reason lives.

[E0-28](../tickets/e0/E0-28-review-debt-from-e0-15.md) item 3 is related and is
not this: a Moodle line item id carries a query string, so `id + "/scores"` is
wrong there. Both are "the mock is smoother than reality" findings; this one was
closable in place and that one needs a seeded line item shaped differently.
