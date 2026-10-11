# 0196 — The leadership gate answers a session in another role 403, marked `insufficient_scope`

**Status:** Accepted, amending [0177](0177-the-item-1-registry-sweep-exempts-the-refusals-only-a-leader-can-be-served.md) (the gate now answers a student with one of two sentences, both inside the sweep)
**Date:** 2026-10-11
**Ticket:** [E7-08](../tickets/e7/E7-08-leadership-not-your-role.md)

## Context

`app.api.deps` has three role gates, and each answered one 401 to every
refusal: no token, a malformed one, an expired one, one signed with another
key, and a real session in another role. The reason is in the gates' comments:
an answer that told "signed in as somebody else" from "not signed in" would
tell a caller trying tokens that one of them was real. Sessions are signed
tokens with no server-side record ([0089](0089-the-session-both-doors-issue-and-the-launch-nonce-ledger.md)),
and the role in one was decided at the door from the person's own rows
([0098](0098-the-landing-comes-from-the-assignment-model.md)).

The leadership pages read every 401 as an ended session. A student or an
instructor who follows a link to a leadership page is signed in, and was told
their session had ended. Ruling 11 of the E7 breakdown settles that a real,
verified session in another role gets 403 from the leadership gate and that the
pages say "not part of your role". The spec does not say why this gate differs
from the other two, or how a page tells the gate's 403 from the other 403s the
same routes answer; this record does.

## Decision

**Only `require_leadership` changes**, and `csrf_verified_leadership` with it,
because it declares that gate as its dependency. It refuses in a fixed order.
First, `session_from_request` verifies the signature and the expiry and
collapses the four failures into `None`; each gets the same 401, the same
`Bearer` challenge and the same `NOT_LEADERSHIP` sentence as before. Only after
that is the role read, and a verified, live session in any role but leadership
gets 403 with one sentence, `app.copy.leadership_sets.NOT_YOUR_ROLE`, the same
for every role and route. The role is never read off a token that has not
verified, so a forged or expired student token still gets the 401.

The 403 tells a caller only that the token they already hold is a real
session, which they could learn from the role it was issued for. It names no
route, section, person or role.

**The student and instructor gates keep one 401.** The ticket gives the
reason: the leadership gate is the only one a person in another role reaches
from a link in the product, so it is the only one whose 401 was misread by a
person who is signed in.

**The 403 carries `WWW-Authenticate: Bearer error="insufficient_scope"`**
(RFC 6750 section 3.1, the standard answer for a valid token that lacks the
privilege). Those routes already answer 403 for other reasons: a leader with
no review grant (ADR [0190](0190-a-lead-reviews-flagged-text-at-any-threshold-and-the-log-withholds-held-text.md)),
another leader's set on a write, and a write without its double-submit token.
Each carries its own sentence, which the pages show, and none carries a
challenge. `frontend/src/api/leadership.ts` reads a 403 with that challenge as
`not-your-role` on every call, and the review queue, the exclusion log and the
comparison-set pages render "This page is not part of your role" for it. A 401
still renders the ended-session sentence, which now opens with the same words
on all three pages.

## Alternatives rejected

- **Every 403 means "not your role" on the page.** Simplest, and wrong: a dean
  at the review queue would be told the page is not part of their role, where
  ADR 0190 gives them the server's own sentence, and a leader refused a write
  on another leader's set would lose the reason.
- **The frontend compares the body to a copy of the sentence.** A second copy
  of the backend's words, which drifts the first time either is reworded.
- **A machine code in the body.** The body is one sentence under `detail` and
  nothing else, so a refusal has nowhere to name anything; a second member
  breaks that rule.
- **The same change in all three gates.** The other two are not reached from a
  link by a person in another role, so they would give up the one-answer
  property for no reader.

## Consequences

- A caller holding a real session learns that it is real from a leadership
  route, as it already could from the role it was issued for. Tokens that do
  not verify remain indistinguishable from each other.
- `NOT_YOUR_ROLE` is a second sentence the gate can serve a student, so it is
  inside SPEC §4.1 item 1's registry sweep, like `NOT_LEADERSHIP`, and not in
  ADR 0177's exempt tuple.
- A future leadership route gets both answers by declaring either dependency.
  A future 403 on these routes must not carry the `insufficient_scope`
  challenge, or the pages will read it as "not your role".
