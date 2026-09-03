# 0114 — A comment the provider cannot be asked about refuses; it does not floor

**Status:** Accepted
**Date:** 2026-09-01; the bounced-text question it left open was ruled 2026-09-03
**Tickets:** E2-08; E2-13 for the ruling

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
422**, carrying the verdict and that verdict's coaching copy, and storing no
response and no answer. 422 rather than 400: the request was understood and its
content was not acceptable, which is the same reading every other value refusal on
this route takes. The verdict rides in the body rather than in the status because
there are two verdicts and §3.3 requires two different sentences.

**A bounce keeps the classification that produced it, against no answer.** Added
2026-09-02 by this ticket's security round. The gate runs before anything is
written, so a bounced submission creates no response and no answer to roll back,
and the verdict — a model's or the character floor's alike — is recorded with
`answer_id` NULL, which ADR 0055 already permits ("the row names no comment"). The
row is the record SPEC §7.4 rests auditability on: "a specific prompt version and
model ID produced a specific classification". A student bounced three times is
three model calls that were made, answered and paid for, and discarding them is
the one way to lose an append-only row that ADR 0055's grant cannot prevent —
`UPDATE` and `DELETE` are withheld, and a row that is never committed needs
neither.

The rest of the route's answer table follows the same principle and is recorded
here so it is in one place: **403** when a cookie-borne submission carries no
valid `X-Pulse-CSRF` token (added 2026-09-02 by the security round — ADR 0089
settles the double-submit mechanism, the header and the binding to `jti` and
settles no status; 403 rather than 401 because the session is *valid* and the
request is not, so a `WWW-Authenticate` challenge would invite the client to
re-present a credential that was already correct, and a Bearer-authenticated
request is exempt by construction because no cross-site page can make a browser
attach an `Authorization` header); 401 for a request with no student session; 404
for a section the student cannot reach *and* for a section id that names nothing
(SPEC §4.1 item 1 — the two must be indistinguishable); 409 for a closed window,
for the duplicate the uniqueness constraint refuses, and for the withdrawal
[ADR 0115](0115-a-resubmission-revises-its-answers-in-place.md) refuses; and 422
for every value the question rows reject, for a comment over the 4000-character
bound the request model carries, and for the bounce above.

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

**Discarding a bounce's classification with the rest of the transaction.** The
natural shape, and the one this route shipped with until the security round: raise,
and let the request's transaction roll back. It makes every other assertion about a
bounce pass — nothing is stored, which is what §3.3 asks — and it silently drops
the audit row §7.4 requires, through a mechanism nobody chose rather than a
decision anybody made.

**Storing the bounced comment's text beside the preserved verdict**, so that a
refused comment could be moderated. ADR 0055 refused a comment fingerprint on
`classification` on confidentiality grounds, and storing the text itself is a
larger version of the same question. This record left it open when it was first
written, because the answer is a safety decision the spec does not make; it was
ruled on 2026-09-03 and the text is not stored. The ruling and the grounds it was
accepted on are in the consequences below.

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

**The bounce's status is pinned by this record and asserted by the suite.**
E2-08's tests asserted only "a client error, the registry's coaching text, nothing
stored" while the number was open; the security round ruled 422 and the tests now
assert it, so a bounce that starts answering 400 or 409 is a change somebody makes
deliberately and moves this paragraph with.

**Keeping the bounced verdict makes those rows unbounded per attempt**, since
nothing limits how often a student may be coached and try again — they are
unlinkable by design (`answer_id` NULL, and no user, section, week or comment text
on the row), reachable only with a live enrollment, one already-paid provider call
each, and unable to move `response.is_valid` or enter the re-classification sweep,
but they do land in any aggregation over `classification` that does not exclude
them, §6.1's drift panel included; `docs/tickets/e2/deferred.md` carries the
linkage-or-cap ruling that would close it.

**A bounced comment's *text* is outside the reach of §5.2's moderation and §6.2's
Care queue, and that is the accepted cost of the decision below.** The verdict is
kept and the words are not: `classification` carries no comment text and ADR 0055
refused even a fingerprint of one, "recoverable by dictionary in seconds" over
strings this short. So a comment that is bounced as `nonsense` — or as
`insufficient` — is never stored anywhere, and the moderation pass that routes a
threat or a self-harm disclosure to Care (§6.2) runs over stored comments. A
student whose comment discloses harm and is bounced for being too brief is a
student the Care path never sees, and "the answers are still in the form" is not
the same as anyone having read them.

**Bounced comment text is not stored. Ruled 2026-09-03, and this paragraph is the
record of it.** The question was left open when this record was first written,
because both directions are safety decisions the spec does not make: §6.2 says a
Care disclosure must reach the queue, while §4 and ADR 0055 say a student's words
are stored in one place under one set of rules, and storing refused text creates a
second — with a retention question, a grant question and a reveal question of its
own. Three grounds were accepted with the ruling, and two of them are guards
that MATURE in later epics rather than facts about today — the E2 boundary
review's security pass caught an earlier version of this paragraph stating
them in the present tense, and this paragraph is the corrected record. **Today
no comment is screened for harm at all**: the submit path runs the validity
classifier only, the moderation pass that will route a threat or a self-harm
disclosure to Care (§5.2, §6.2) is E6's and E10's and is called from nothing,
so a bounced comment is unscreened exactly as every stored comment is
unscreened. The grounds, honestly tensed: **when the moderation pass exists,
text the classifier judges harmful will be screened from the stored path** —
§3.3's gate bounces `insufficient` and `nonsense` only, so a disclosure long
enough to be judged substantive is submitted and stored, and the exposed case
is a disclosure short enough or garbled enough to be refused. **E10's recall
floor, when it is set, is the guard on mislabeling** that narrow case: a
disclosure classified as `nonsense` is a recall miss, and SPEC §9.3 makes that
rate a hard gate once E10 gives it a set and a value — today
`tests/evals/threat/floors.py` is a deferred declaration with no cases, which
is the refuse-to-silently-pass structure E2-12 built, not a measurement. And
**a student's words stay in one store under one set of rules**, which is the
property §4 and ADR 0055 are built on and the one a second store would end.
The alternative — a store for refused text, with its own retention, grant and
reveal rules — is refused for a case the maturing grounds narrow to a measured
rate on a gated surface. **What schedules the revisit, since a rate nobody
measures can never be missed**: `docs/tickets/e3/carried-from-e2.md` hands E10
a named check — its threat-floor work takes the bounce-before-screening path
into the floor's scope or reopens this ruling. It also reopens if §3.3's
bounce set widens beyond `insufficient` and `nonsense`.

**E2-10's form has a contract it can build against.** A 403 means "reload and try
again"; a 503 with `Retry-After` means "keep what is on screen and offer to retry";
a 422 with a verdict means "show this sentence beside the comment field"; a 409
means "reload, the week has moved". Nothing in that list requires the form to read
a message and guess.
