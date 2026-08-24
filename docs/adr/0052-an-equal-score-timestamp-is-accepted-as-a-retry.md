# 0052 — An equal score timestamp is accepted as a retry

## Context

AGS 2.0 has a platform refuse a score whose `timestamp` is **before** the one it
already holds for that user on that line item, and answer `409 Conflict`. The
rule exists because a passback arriving out of order would otherwise overwrite a
newer grade with a stale one.

The specification says nothing about a timestamp that is *equal* to the one held.
"Not later" and "strictly earlier" are both plausible readings of one sentence,
and they differ on exactly one case — which is the case E3 will produce most
often.

SPEC §3.4 recomputes and re-posts a section's participation score after every
week closes, and E3 adds retry handling on top. The retry that matters here is
the one after a **network timeout**: the tool sent a score, never learned whether
it arrived, and re-sends the identical body — same `userId`, same `scoreGiven`,
same `timestamp`, because the timestamp names the recomputation rather than the
attempt.

This suite asserted the opposite reading for a day. The test that turned around
says so in its own docstring, which is why this record exists rather than a note.

## Decision

A score whose `timestamp` is **strictly earlier** than the one held is refused
with `409`. A score whose `timestamp` **equals** the one held is accepted: it is
appended to the log beside the score it repeats, and it updates the `Result`.

The comparison is between instants rather than strings or dates. That follows
from the boundary rather than decorating it — once equal is accepted, a guard
that truncated to the minute, or compared date halves, is right about a score
from last year and wrong about one a second early, and a second is now the whole
width of the rule.

## Alternatives rejected

**Refuse equal too, reading "before" as "not after".** The safe-sounding reading,
and it breaks the case the rule is most likely to meet. A platform answering
`409` to a timed-out retry has told the tool *its retry failed* while the score
is sitting in the platform's log. E3's branch on `409` is "the platform holds
something newer, stop retrying" — which is exactly the wrong conclusion here, and
the tool has no way to tell the two apart, because the status is the same.

**Accept equal but replace the earlier entry rather than appending.** Tempting
because two entries with one timestamp look like duplicates. It contradicts
E0-15's ruling that the store is a log rather than a table keyed by student: the
sequence is the only evidence E3 has that a repost happened at all, and a store
that collapses a retry has thrown away the one thing its retry handling needs to
prove. It is also unobservable in the case that motivates it — an identical body
replacing an identical body changes nothing anyone can see — so the behaviour
would be decided by a test that could not fail.

**Deduplicate on the whole body, so an identical retry is a no-op and a differing
one at the same instant is refused.** The most conformant-looking option, and the
most fragile: it makes the platform's answer depend on byte equality of a JSON
document, so a tool that reordered its keys or rendered `61.5` as `61.50` between
attempts would get a `409` for a retry. It also puts a rule in the mock that no
real platform implements, which is the thing this service exists not to teach.

**Leave it undefined and let whichever arrives first win.** That is what the
service did before the ordering rule existed, and it is how a stale score
overwrote a newer grade — the defect the `409` was added to close. The boundary
has to be somewhere; leaving it unstated means it is decided by an implementation
detail nobody wrote down.

## Consequences

**The mock is more permissive than a strict reading of AGS here**, which is the
opposite direction from
[ADR 0051](0051-a-disagreeing-score-maximum-is-refused-rather-than-rescaled.md)
in the same round. That asymmetry is deliberate and worth naming: the maximum
rule narrows the specification to stop a wrong grade being produced silently,
while this one fills a gap the specification leaves. A tool written against this
platform and run against one that refuses equal timestamps would see a `409` it
does not expect — so **E3 must treat `409` as "stop retrying and re-read", not as
an error to surface**, which is the right handling in both worlds.

**A repeat at one instant lands twice in the log**, and a reader of
`GET /mock/posted-scores` sees two entries carrying the same timestamp. That is
the record doing its job: it is what shows a retry happened, and the sequence is
what distinguishes it from a single delivery.

The rule is asserted from both sides — a score one second earlier is `409`, a
score at the same instant is accepted and its value wins — so a later
implementation cannot slide the boundary without a red test naming it.
