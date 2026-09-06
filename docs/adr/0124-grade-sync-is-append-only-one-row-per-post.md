# 0124 — `grade_sync` is append-only, one row per post

## Context

SPEC §8 names `grade_sync` in its table list and describes none of it. E3's
breakdown had to decide the grain before E3-02 builds the table, because
everything downstream reads it: E3-06's sweep compares the computed score
against what was last sent, and E3-04's retry handling re-sends a value that
has to be byte-identical to the delivery it retries
([0052](0052-an-equal-score-timestamp-is-accepted-as-a-retry.md)).

The obvious grain is one row per `(section_id, user_id)` holding the last
value sent, updated in place on each post. That is what the breakdown first
recorded, and it is wrong for a reason the item-based formula introduced.

**A posted score is not final when its week closes.** The participation score
ruled on 2026-09-04 counts completed items, and a comment item counts only
while its most recent classification is outside §3.3's refused set. E2-08's
asynchronous re-classification sweep can flip a comment that fell to the
fail-open floor from substantive to `insufficient` weeks after the window
shut, which lowers the numerator of a score already posted. E3-06 therefore
re-posts whenever a recomputation changes the value.

Under a last-value grain, that re-post overwrites the row. The value the
platform was previously told — the number a student saw in a gradebook, the
number an instructor may have acted on — is then gone from Pulse entirely.
The LMS gradebook is a third-party system of record that Pulse writes to and
cannot read back reliably, and a tool that writes to someone else's record of
a student's standing while keeping no account of what it wrote cannot answer
the one question that matters when the number is disputed: what did we send,
and when.

## Decision

`grade_sync` is **append-only, at the grain of one row per post**. Each row
records the score as it was sent — the exact string, not a number to be
re-rendered — the timestamp sent with it, the outcome of the call, and the
student and section it concerns.

The **latest row for a `(section_id, user_id)` pair** is what serves
[ADR 0052](0052-an-equal-score-timestamp-is-accepted-as-a-retry.md)'s retry
identity and what E3-06 compares against to decide whether the computed value
has changed. So the query the sweep runs is a lookup of the most recent row
rather than a read of a single stored one, and the history sits behind it at
no extra cost to the write path.

A failed post is a row too. An attempt that never reached the platform is
part of the account of what Pulse tried to do to a gradebook.

## Alternatives rejected

**One row per `(section_id, user_id)`, holding the last value sent, updated
in place.** The cheaper read and the smaller table, and it satisfies the
retry identity perfectly well — which is why it was the first choice. It
fails on the case the epic is built around: an update destroys the previous
posted value, so after a re-classification lowers a score there is no record
that the higher one was ever sent. A score that changed by itself is exactly
the score someone asks about, and the answer would have to be reconstructed
from `ags_call` bodies or not at all.

**Keep the last-value row and rely on `ags_call` for history.** Tempting,
because `ags_call` logs every HTTP call and a post is an HTTP call. It
conflates two records with different jobs and different lifetimes: `ags_call`
is an operational log for §6.1's console, sized and retained for diagnosing a
failing integration, while this is the account of what a student was told
their participation was. Deriving one from the other means parsing request
bodies to answer a question about grades, and it makes any future retention
rule on the call log silently a retention rule on the grade history.

**Append-only, but at the grain of one row per student per week.** Closer,
and initially attractive because it looks like the ledger. It does not match
what actually happens: a post carries a whole-term percentage, not a week,
and a single re-classification in week 3 changes the one posted number rather
than a per-week row. Storing per-week rows would mean deriving the posted
value from them, which puts the arithmetic in two places and reintroduces the
re-derivation problem ADR 0052 warns about.

**Store nothing, and read the platform's current score before each post.**
Removes the table and looks conformant. It makes every sweep a round trip per
student against a third-party service, it depends on a read scope a platform
may not grant, and it still cannot answer what Pulse sent last week — only
what the platform holds now, which a human may have edited.

## Consequences

**The table grows with posts rather than with students.** A section of thirty
students over a fifteen-week term posts on the order of hundreds of rows,
plus re-posts. That is small, and it is bounded by the sweep's
post-on-difference rule: a run that changes nothing writes nothing. A
retention rule for these rows is a decision nobody owes today, and when one is
needed it belongs with §4's retention work rather than here.

**Every reader must ask for the latest row and not for "the" row.** That is
the failure mode this grain introduces, and it is the shape
`docs/MISTAKES.md` entry 3 keeps recording: a query that happens to return one
row in a test fixture and the wrong row in a term's worth of data. E3-02 owes
an index that makes the lookup cheap and a test that plants a second row and
requires the newer one to win.

**A failed post and an absent post become distinguishable**, which is what
lets E3-06 leave a section in a state an operator can act on and what gives
E11's job dashboard something true to render.

**The history is a record about students**, so the `PERSON_TABLES` standing
question is asked of this table with more care than of `ags_call`. It holds
an LMS user id and a participation figure, which is a statement about a named
person's standing even though it holds no name — E3-02 answers the question in
its pull request body with the columns the judgement was made against.
