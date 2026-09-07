# 0153 — A release drops its week, because the gradebook's own ledger would otherwise name the author

## Context

This record is owed. `docs/tickets/e4/carried-from-e3.md` carries "Comment
de-anonymization by completion pattern", accepted in
[0125](0125-the-score-comments-per-week-ledger-is-instructor-visible.md), with a
done-when this ticket has to satisfy:

> **Done when:** each states in writing that its suppression holds against a
> reader who also has the gradebook open, or changes what it suppresses.

So the reader this record is written about is not a stranger. It is an instructor
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

## Decision

**A released comment carries no week attribution anywhere, and the report groups
releases under no week.** `ReportComment` has three fields — `text`, `status`,
`stream` — and is frozen; `released_comments` answers a flat
`tuple[ReportComment, ...]` rather than a mapping keyed by week or a nesting of
per-week tuples; and the view underneath returns no instant of any kind. E4-07
renders the result in the latest published week's report, under a from-earlier-
weeks heading, which is a placement rather than an attribution.

**The statement the carried entry asks for, made against the sharpest reader.**
Take the instructor with the gradebook open, and take the term's *worst* case for
us: a section of four students, all four of whom answered in week 3, one of whom
wrote a comment.

*If a release named its week*, that instructor reads the released comment under
"Week 3", opens the gradebook, and sees which students completed week 3's comment
item — "4 of 5" against "3 of 5" is the distinguishing fact, and it is per
student. In a section that size the intersection of "completed the comment item
in week 3" and "wrote the one comment held from week 3" is frequently one person,
and where it is not one it is two or three. That is not a re-identification
attack; it is arithmetic on two screens the instructor is entitled to see, and
§4's promise to the student who wrote that comment is gone.

*Because a release names no week*, the same instructor has a comment known only
to have come from *some* under-threshold closed week in this section's term so
far. The candidate set is the union of every such week's comment-writers, and it
grows with each week the term runs. The batch is what makes that union real
rather than nominal: §4 says the comments surface "batched so that timing cannot
identify an author", and a batch cut on a Monday for a whole term's held set is a
fact about a *set of weeks*, not about a comment.

**The cadence is part of the statement.** Every batch in the institution is cut
by one weekly task in the same handful of minutes
([0152](0152-the-crossing-is-cut-by-a-task-of-its-own-not-at-read-time-and-not-by-the-summary-job.md)),
so `cut_at` distinguishes nothing within a batch and little between sections. A
release cut at submission time, or re-derived at read time, would have put the
week back through the clock after this record had taken it out of the payload.

**What residual narrowing is accepted, stated rather than elided.** The candidate
set is the union of the term's under-threshold closed weeks *so far*, and early
in a term that union is small. A section whose first crossing happens in week 3
has released comments drawn from at most two under-threshold weeks, and if only
one of those weeks held comments at all, the release names that week by
elimination — the instructor knows which weeks were small and which held nothing,
because the report shows every week's distribution and its response count. In the
worst arrangement — a first crossing over a single held week in a four-response
section — the released set is exactly that week's comments and dropping the label
buys nothing.

**That residual is accepted, and here is the boundary at which it would not be.**
It is accepted because the alternative that would close it is worse for the same
student: holding the release until the union is large enough would mean a
threshold on top of a threshold, with a comment surfacing later or never, and §4
already commits to surfacing these comments. It is bounded, because the same
arithmetic that makes the set small also makes it small for a single week's
ordinary above-threshold comments, which §4 shows without a batch at all. And it
shrinks monotonically: every further under-threshold week widens the set, and
nothing narrows it back.

What would change the answer is a *stated* narrowing rather than an inferred one.
If a later surface displayed which weeks a release drew from, or how many
comments came from each week, or ordered a release in a way an instructor could
map onto weeks, the reasoning above stops holding and this record is re-read —
exactly as ADR 0125 says of a ledger line that started naming a question.

## Alternatives rejected

**Keep the week and argue the ledger is acceptable**, which is criterion 5's
other branch and the shape E4-04's ticket required to be argued if it won. It
cannot be argued honestly here. ADR 0125's acceptance rests on the ledger being a
*completion* signal the gradebook already carries — a fact about participation,
not about content. Joining it to a week-attributed comment converts it into a
fact about content, which is the thing it was accepted for not being. An ADR that
kept the week would have to claim §4's small-N rule survives an inference §4
exists to prevent.

**Keep the week but only for weeks above some size.** It gets the arithmetic
right and creates a worse artefact: the presence or absence of a week label is
then itself a signal about how small the week was, on exactly the comments §4 is
protecting. A rule whose *application* leaks the fact it is protecting is a rule
that has moved the leak rather than closed it.

**Group a release by stream only, which is what happens, but keep the week inside
the payload for the payload layer's use.** This is the version somebody writes:
the field exists, nothing renders it. It is rejected on the same ground ADR 0146
rejects a `released_at` column — "a stored timestamp nobody exposes today is a
leak someone ships tomorrow" — and one ground more: `ReportComment` is what E4-07,
E4-10 and every later surface receives, and a field on it is an invitation the
next author has no reason to refuse. The absence is structural for that reason,
asserted as an equality over the whole field list rather than as a search for a
name.

**Delay a release until its candidate set exceeds some size**, closing the
residual named above. It is the only alternative that would actually close it,
and it costs the student whose comment it is: a section with one held week early
in the term would hold that comment indefinitely, and a term that never crossed
again would never surface it. §4 promises these comments surface once the volume
crosses; adding a second, unstated threshold to a rule the spec has already
written is a change to the spec, not an ADR's to make.

**Suppress released comments from the report entirely and leave them to the
summary.** Safest, and it deletes a §4 sentence: the comments "surface as raw
text" is the whole of what the cumulative rule is for. A section whose students
wrote through a run of quiet weeks would have their words reach nobody.

## Consequences

- **The carried entry's done-when is satisfied for E4 by this file**, in the
  first of its two directions: this epic states in writing that its suppression
  holds against a reader with the gradebook open, and names the residual it does
  not close. **E6 still owes its own half.** Its moderation views put comments
  beside a roster with reviewer decisions attached, and nothing here covers that
  surface; the entry stays open against E6 until it writes the same statement.
- **A released comment cannot be placed back into its week by any later
  ticket without reopening this.** The field does not exist, the container does
  not carry it, and `tests/integration/test_a_released_comment_carries_nothing_that_names_its_week.py`
  asserts both as invariants in the isolated §4.1 pass.
- **E4-07 must not order a release by anything derivable from a week.** The order
  is randomized behind an rng seam in `app.services.report_comments` and no
  stored order reaches a caller; a payload layer that re-sorted a release — by
  text, by length, by anything stable — would hand back an order, and an order is
  a channel.
- **The residual is real and is now written down where the next reader meets
  it.** A section's first release, early in a term, may be attributable by
  elimination. Nobody is claiming otherwise, and a later ticket that wants it
  closed has this record's last alternative as its starting point.
- **The instructor loses information they might reasonably want.** "Which week
  was this about" is a fair question about feedback, and the answer is now
  unavailable for released comments. E4-07's from-earlier-weeks heading is what
  says so honestly on the page, rather than letting the reader assume the
  comments are about the week they are reading.
