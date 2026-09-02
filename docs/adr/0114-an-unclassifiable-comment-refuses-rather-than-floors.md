# 0114 — A comment the provider cannot be asked about refuses; it does not floor

**Status:** Accepted
**Date:** 2026-09-01
**Tickets:** E2-08

## Context

SPEC §3.3 sanctions one fail-open in this system:

> Classifier latency budget: p95 < 2s; on provider timeout, the heuristic floor
> applies and the submission is accepted, then classified async (fail open, never
> block a student on an outage).

[ADR 0056](0056-what-fails-open-what-raises-and-what-the-provider-url-may-carry.md)
turned that sentence into a table of four exception classes.
`AIProviderUnavailableError` — a read or write timeout, or HTTP 408/502/503/504 —
floors, and `app.ai.tasks.classify_comment_validity` absorbs it and returns the
character floor. The other three raise out of the classifier:
`AIProviderUnreachableError` (a connection that reached no endpoint),
`AIProviderRefusedError` (a status about our own request — 401, 403, 404, 429, 500
and anything else), and `AIResponseInvalidError` (an answer that was not the
contract, twice).

ADR 0056 deliberately stopped there, and said so twice. Its consequences: "E2 owns
the submit path and has to answer for it deliberately: catching `AIGatewayError`
there is a decision with a student on the other end of it, and it is not E0-13's to
make on E2's behalf." And, arguing for keeping 429 and 500 outside the floor: "The
cost of raising is the opposite and much louder: E2 sees the error on the submit
path and answers for it." `app/ai/tasks.py`'s own docstring says the same in as many
words. So this decision is E2-08's, it was left open on purpose, and a reasonable
engineer could go either way on it.

The same route also has an error contract to settle for the case §3.3 *does*
specify in words but not in a status code: what a bounced submission answers with.
That is the second half of this record, because it is the same route's answer table
and separating them would leave a reader with half of it.

## Decision

**A provider failure ADR 0056 keeps outside the floor is an honest retryable
refusal: HTTP 503, `Retry-After: 60`, the `submit.classifier_down` sentence from
`app.copy`, and nothing stored.** The three classes are enumerated at the submit
path — never their common base — and the response and its answers are rolled back
before the refusal is raised, so the student's answers are still in the form in
front of them and no row exists that they were not told about.

**A comment the classifier judges `insufficient` or `nonsense` bounces with HTTP
422**, carrying the verdict and that verdict's coaching copy, and storing nothing.
422 rather than 400: the request was understood and its content was not acceptable,
which is the same reading every other value refusal on this route takes. The
verdict rides in the body rather than in the status because there are two verdicts
and §3.3 requires two different sentences.

The rest of the route's answer table follows the same principle and is recorded
here so it is in one place: 401 for a request with no student session, 404 for a
section the student cannot reach *and* for a section id that names nothing (SPEC
§4.1 item 1 — the two must be indistinguishable), 409 for a closed window and for
the duplicate the uniqueness constraint refuses, and 422 for every value the
question rows reject.

## Alternatives rejected

**Floor on every failure to classify.** The simplest rule and the one ADR 0056
exists to refuse. It hands the decision "does this comment get classified" to
anybody who can drop packets on the path — ADR 0056: "A connect timeout is in this
group *because* it is the cheapest thing an attacker can force." It also makes a
permanent misconfiguration invisible: a wrong base URL, a rejected credential or a
model name that does not exist would degrade every comment in the institution to a
character count, silently, for as long as it took somebody to notice that no
comment had been classified since Tuesday.

**Answer 500 and let the exception escape.** Honest about the fact that something
broke, and useless to the student: no `Retry-After`, a stack trace in the log
against a request the student did nothing wrong in, and a page that reads as "this
tool is broken" rather than "try again shortly". It also loses the one thing this
refusal has to say, which is that the answers were not thrown away.

**Accept the submission and mark it invalid.** Rejected outright: §3.3's whole
point is that a student is told *before* submission and "never silently penalized
after the fact". Storing a response nobody could judge and calling it invalid is
that sentence's exact opposite.

**Accept the submission and classify it entirely async**, as if the floor had
applied but without recording a floor. This is the tempting middle, and it fails on
what ADR 0054 spends the audit pair for: a floored row says a floor decided it, and
the async sweep finds those rows *by that pair*. A response stored with no
classification at all is a response nothing will ever come back to.

**A shorter or longer `Retry-After`.** Sixty seconds is a length of time a student
will actually wait, and it is long enough that a retry does not arrive inside the
same provider blip. Ten would invite a retry storm from a form nobody has closed;
five minutes would end the session. It is not a setting: an operator who could turn
it up would be spending a student's time, and there is one right answer for a blip.

**409 for the bounce**, on the reading that the comment "conflicts" with the gate.
Rejected because 409 on this route already means "the state of your week is not
what you think it is" — a closed window, a response another request stored — and a
bounce is neither.

## Consequences

**A provider that is down in a way ADR 0056 does not floor blocks submission
entirely**, for as long as it is down. That is the deliberate half of this record
and not a gap: it is loud, it names itself in the response and in the logs, and an
operator finds out within one class period rather than a term later. The narrower
case — a hosted provider's ordinary outage — answers 502 or 503 and floors, which
is what §3.3's sentence was written for.

**The two answers are one digit apart at the provider and very far apart for the
student**, so the near-miss pair is the test that keeps them honest: a mock told to
answer 503 floors and stores the submission; the same mock told to answer 500
refuses with this record's 503 and stores nothing. Both run against the stack, and
so does the unreachable row, whose address is a closed loopback port because a mock
that answers cannot mint a connection that fails.

**The bounce's status is now pinned by this record rather than by the tests.**
E2-08's suite deliberately asserts only "a client error, the registry's coaching
text, nothing stored", so 422 is this record's to change; a later ticket that moves
it moves this paragraph with it.

**E2-10's form has a contract it can build against.** A 503 with `Retry-After`
means "keep what is on screen and offer to retry"; a 422 with a verdict means
"show this sentence beside the comment field"; a 409 means "reload, the week has
moved". Nothing in that list requires the form to read a message and guess.
