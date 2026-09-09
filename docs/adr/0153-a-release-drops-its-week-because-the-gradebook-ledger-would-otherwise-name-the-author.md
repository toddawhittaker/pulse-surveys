# 0153 — A release drops its week, because the gradebook's own ledger would otherwise name the author

## Context

This record is owed. `docs/tickets/e4/carried-from-e3.md` carries "Comment
de-anonymization by completion pattern", accepted in
[0125](0125-the-score-comments-per-week-ledger-is-instructor-visible.md), with a
done-when this ticket has to satisfy:

> **Done when:** each states in writing that its suppression holds against a
> reader who also has the gradebook open, or changes what it suppresses.

The reader this record is written about is not a stranger. It is an instructor
who is entitled to everything they can see, holding two things at once: the
Monday report SPEC §5.1 gives them, and the gradebook column SPEC §3.4 posts
into. That column carries a per-week participation score and, beside it, a
comment reading like "Week 3: 4 of 5 items" — a completion ledger, per student,
per week. ADR 0125 accepted it on the ground that a weekly-updated score already
carries the same signal through its deltas, and that the ledger says nothing
about *what* anybody wrote.

E4-04's own ticket states the sharp version of what that acceptance does not
cover, and makes the answer a decision rather than a rendering detail:

> a released under-threshold comment is grouped under a week, the ledger says who
> completed that week's comment items, and the intersection can be small.
> … Whether the release preserves week attribution is therefore not a rendering
> detail — it is the decision the statement stands on.

**And there is a second reader, which this record's first writing did not
consider and E4-04's security review did: the same instructor next Monday.** A
report is read weekly. What that instructor holds is not one page but a
*sequence* of pages, and the difference between two of them is information
neither page carries on its own. Dropping the week from the payload does nothing
about that delta by itself — it has to be true of the batches as well, and the
first build's release gate did not make it true. That is what
[0152](0152-the-crossing-is-cut-by-a-task-of-its-own-not-at-read-time-and-not-by-the-summary-job.md)'s
layered gate is for, and this record now stands on it.

## Decision

**A released comment carries no week attribution anywhere, and the report groups
releases under no week.** `ReportComment` has three fields — `text`, `status`,
`stream` — and is frozen; `released_comments` answers a flat
`tuple[ReportComment, ...]` rather than a mapping keyed by week or a nesting of
per-week tuples; and the view underneath returns no instant of any kind. E4-07
renders the result in the latest published week's report, under a
from-earlier-weeks heading, which is a placement rather than an attribution.

**And no batch may be one week's worth, or fewer than a threshold's worth of
people.** That is ADR 0152's gate, restated here because it is half of what this
record's argument rests on: every batch this system can cut draws from at least
two distinct under-threshold closed weeks and carries the comments of at least
`n_threshold_default` distinct authors. Without it the payload's silence about
weeks was undone by the report's own arithmetic, which is the finding below.

### The statement the carried entry asks for, made against both readers

**The reader with the gradebook open, on one page.** Take a section of four
students, all four of whom answered in week 3, one of whom wrote a comment.

*If a release named its week*, that instructor reads the released comment under
"Week 3", opens the gradebook, and sees which students completed week 3's comment
item — "4 of 5" against "3 of 5" is the distinguishing fact, and it is per
student. In a section that size the intersection of "completed the comment item
in week 3" and "wrote the one comment held from week 3" is frequently one person.
That is not a re-identification attack; it is arithmetic on two screens the
instructor is entitled to see, and §4's promise to the student who wrote that
comment is gone.

*Because a release names no week*, the same instructor has a comment known only
to have come from *some* under-threshold closed week in this section's term so
far. The candidate set is the union of those weeks' comment-writers.

**The reader who was also here last Monday.** This is the half the first writing
missed. A release appears on a report that did not have it a week ago, so the
delta between the two reports is itself an attribution channel: whatever closed
in between is where the new comments came from. Under a volume-only gate that
channel was exact — after a section's first release the only thing ever held was
the week that had just closed, so every subsequent batch was one week's worth,
and the delta named the week precisely with the label removed from the payload
and restored by the calendar.

Under the gate ADR 0152 settles, that delta is bounded from below rather than
exact:

- **A batch spans at least two distinct under-threshold closed weeks**, so the
  set a delta points at is never a single week.
- **A batch carries at least `n_threshold_default` distinct authors**, so the
  candidate set behind a released comment is never smaller than the number §4's
  threshold names — the same floor §4 applies to a week's comments shown under
  their own heading.
- **Every batch is cut by one weekly task in the same handful of minutes**
  (ADR 0152), so `cut_at` distinguishes nothing within a batch and little between
  sections.

So the strongest thing a repeat reader can say about a released comment is that
it came from one of at least two quiet weeks and was written by one of at least
`n_threshold_default` people. Both floors are properties of every batch the
cutter can write, not of the batches that happen to exist today.

**What residual narrowing remains, stated rather than elided.** The candidate set
is the union of the quiet weeks a given batch drew from, and it is bounded below
rather than made large. A batch of exactly two quiet weeks and exactly
`n_threshold_default` authors is the smallest the gate permits, and an instructor
who knows which weeks were quiet — the report shows every week's response count —
knows that batch drew from two of them. That is a narrower set than "the term",
and it is the honest floor: the guarantee is "no fewer than a threshold's worth of
people, from no fewer than two weeks", not "unattributable".

**Why that residual is accepted.** The floor is the same number §4 already accepts
for an ordinary above-threshold week: a week of exactly `n_threshold_default`
responses shows its comments with the same size of candidate set, under its own
week heading, and §4 calls that safe. A release that meets the same floor while
naming no week is strictly better protected than the ordinary case the spec
sanctions. Pushing the floor higher costs the students whose comments are
withheld, and ADR 0152 records what that costs and why the wait is not bounded by
a timer.

**What would change the answer.** A stated narrowing rather than an inferred one.
If a later surface displayed which weeks a release drew from, or how many comments
came from each week, or ordered a release in a way an instructor could map onto
weeks, or showed a release's own size on a page that also showed each week's, the
reasoning above stops holding and this record is re-read — exactly as ADR 0125
says of a ledger line that started naming a question. Lowering the gate is the
same event: this record's floors are ADR 0152's legs, and weakening one weakens
both records at once.

**Extended 2026-09-09 with a third narrowing, from the same boundary review that
produced the amendment below.** If a released comment's own **stream** were used
to partition the release — a heading per stream over the released list, or two
lists rather than one — the same reasoning fires. A release drawn from two quiet
weeks of four and three respondents is a set of candidate authors; split by
stream, it is two smaller sets, and each is a set of people who answered *that
question* in one of two weeks. §5.1 groups the *week's own* comments by stream and
that is unaffected, because those are a week's comments shown under their own
week; what this narrowing covers is the from-earlier-weeks list, where the
container is the whole of the de-identification. `_released` returns one flat
tuple across both streams today (`app.services.reporting`) and `ReportComment`
carries `stream` because the ordinary per-week grouping needs it — so nothing has
to change, and what is written here is that using that field to partition the
*release* is the event that reopens this record rather than a presentation choice.
Recorded as a LOW from the E4 boundary review.

**Re-read 2026-09-08, on E4-12's credit note.** That clause fired: the note E4-12
first shipped in the report's Participation region said a comment judged too
brief or nonsense "costs that student one item of their participation credit",
which is a stated narrowing of the completion-pattern channel rather than an
inferred one — the reader is the one this record is written about, holding the
week's validity readout on one side and the per-week ledger on the other. The
re-read's conclusion is that the channel itself is not this note's: the readout
and the ledger both pre-date it, and their coexistence is the disclosure ADR 0125
accepted. What the note owed was to stop sharpening it. Reworded, it names
participation credit as a count separate from the validity rate and says that an
unanswered item and a comment that did not count leave an item incomplete alike —
so a ledger deficit no longer maps to a refused comment, and a reader who
followed the note's arithmetic learns that the two are indistinguishable there.
The residual is accepted on that ground and the suppression above is unchanged.

**Amended 2026-09-09: the quiet week's own summary was a channel this record did
not cover, and the floor claim is restated to what is now true.** The E4 boundary
review found it. Everything above is about the *release* — what a comment carries
when it surfaces later, and how few candidate authors stand behind it. A quiet
week also has a **summary**, generated in the same week the comments were held
(SPEC §5.1: "there, the summary is the only comment signal"), and a summary is
prose. A summary that reused a commenter's own words disclosed that comment
immediately, under its own week, to the reader this record is written about — the
one holding the per-week completion ledger — and in a four-response week the
intersection of "wrote a comment this week" and "completed this week's comment
item" is frequently one person. It also disclosed it *twice*: once in the quiet
week's summary and again, verbatim and unattributed, when the release was cut, so
a reader who kept both pages could re-attach a released comment to its week by
matching the phrase. That is the sequence channel this record's last rejected
alternative already names, arriving through a surface nobody had looked at.

**The ruling of 2026-09-09 is that below the n-threshold a summary names themes
only** and may not reuse the commenters' word strings, in its prose or in a theme
label. It is enforced twice, because a prompt instruction is soft: `summary.v2`
asks for it, and `app.services.reporting` refuses to store a small-N summary
sharing a twenty-character normalized run with a comment it was fed, rolling that
section-week back so the week is generated again next run.
[ADR 0162](0162-the-small-n-summary-is-a-second-live-prompt-version-and-a-store-time-guard.md)
records the guard's construction.

**The honest residual, which is not zero.** The guard bounds *verbatim* reuse and
nothing else. A summary that says a week's theme in its own words still narrows an
author the same way any true statement about a four-person week does: an
instructor who knows the section can often tell who raised a point from the point
itself, and no threshold, no bound and no prompt can prevent that. What this
amendment buys is that a *string* an instructor could match — against the release
weeks later, or against a student's own writing elsewhere — no longer crosses.
Theme-level correlation remains, and it remains as it was before this record was
written. So the floor sentence above is restated: it was "no fewer than a
threshold's worth of candidate authors, from no fewer than two quiet weeks", which
was true of the release and was silently read as a statement about the whole
surface. It is a statement about the release. The quiet week's summary has always
been a per-week signal about a set smaller than the threshold, that is what §5.1
asks for, and what changed on 2026-09-09 is only that the signal may no longer be
a quotation.

## Alternatives rejected

**Keep the week and argue the ledger is acceptable**, which is criterion 5's other
branch and the shape E4-04's ticket required to be argued if it won. It cannot be
argued honestly. ADR 0125's acceptance rests on the ledger being a *completion*
signal the gradebook already carries — a fact about participation, not about
content. Joining it to a week-attributed comment converts it into a fact about
content, which is the thing it was accepted for not being.

**Drop the week from the payload and leave the gate alone**, which is what the
first writing of this record did. It is the alternative that looks finished and is
not: the payload says nothing about weeks and the report's week-to-week delta says
it instead, because a volume-only gate cuts a batch per quiet week for the rest of
the term once a section has crossed. The lesson is worth keeping — an attribution
channel can live in the *sequence* of what a surface shows rather than in any one
page of it, and a field-level absence is not a guarantee until the thing that
produces those fields is bounded too.

**Keep the week but only for weeks above some size.** It gets the arithmetic right
and creates a worse artefact: the presence or absence of a week label is then
itself a signal about how small the week was, on exactly the comments §4 is
protecting. A rule whose *application* leaks the fact it is protecting has moved
the leak rather than closed it.

**Group a release by stream only, which is what happens, but keep the week inside
the payload for the payload layer's use.** This is the version somebody writes:
the field exists, nothing renders it. Rejected on the same ground ADR 0146 rejects
a `released_at` column — "a stored timestamp nobody exposes today is a leak
someone ships tomorrow" — and one ground more: `ReportComment` is what E4-07,
E4-10 and every later surface receives, and a field on it is an invitation the
next author has no reason to refuse. The absence is structural for that reason,
asserted as an equality over the whole field list rather than as a search for a
name.

**Suppress released comments from the report entirely and leave them to the
summary.** Safest, and it deletes a §4 sentence: "they surface as raw text" is the
whole of what the cumulative rule is for. A section whose students wrote through a
run of quiet weeks would have their words reach nobody.

## Consequences

- **The carried entry's done-when is satisfied for E4 by this file**, in the first
  of its two directions: this epic states in writing that its suppression holds
  against a reader with the gradebook open — and against that reader a week later
  — and names the floor it does not go below. **E6 still owes its own half.** Its
  moderation views put comments beside a roster with reviewer decisions attached,
  and nothing here covers that surface; the entry stays open against E6 until it
  writes the same statement.
- **This record and ADR 0152 now depend on each other.** The week-level guarantee
  is that gate's legs (b) and (c), so a later ticket that relaxes the gate is
  changing this record's argument whether or not it opens this file. Both say so.
- **A released comment cannot be placed back into its week by any later ticket
  without reopening this**: the field does not exist, the container does not carry
  it, and the invariant-marked module in the isolated §4.1 pass asserts both.
- **E4-07 must not order a release by anything derivable from a week.** The order
  is randomized behind a private hook in `app.services.report_comments` and no
  stored order reaches a caller; a payload layer that re-sorted a release — by
  text, by length, by anything stable — would hand back an order, and an order is
  a channel. The hook is private for the same reason: a caller-fixable seed makes
  two reads diffable, and diffing two shuffles of a known set re-derives the order
  the rows arrived in.
- **The residual is real, bounded, and written down where the next reader meets
  it**: no fewer than a threshold's worth of candidate authors, from no fewer than
  two quiet weeks. Nobody is claiming it is unattributable.
- **The instructor loses information they might reasonably want.** "Which week was
  this about" is a fair question about feedback, and the answer is unavailable for
  released comments. E4-07's from-earlier-weeks heading is what says so honestly
  on the page, rather than letting the reader assume the comments are about the
  week they are reading.
