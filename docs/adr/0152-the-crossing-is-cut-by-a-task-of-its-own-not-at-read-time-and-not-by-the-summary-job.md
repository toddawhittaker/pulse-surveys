# 0152 — The cumulative crossing is cut by a task of its own, not at read time and not by the summary job

## Context

SPEC §4 holds a week's comments back when the week is below the n-threshold and
surfaces them later:

> Comments from under-threshold weeks are not discarded — they feed the summary,
> and they surface as raw text once the section's cumulative comment volume for
> the term crosses the threshold, batched so that timing cannot identify an
> author.

E4's breakdown settled that the crossing is *stored* rather than recomputed
(decision 7) and E4-02 built the storage
([0146](0146-a-release-is-a-batch-row-and-a-membership-row.md)). What neither
settled is **who evaluates it, and when**. E4-04's own "Decisions this ticket
settles" leaves it open with a recommendation:

> **Where the crossing is evaluated.** Read-time evaluation re-derives; a job
> evaluates once and writes the batch. The recommendation is the E4-06 job cuts
> batches (it already runs at the only moment volume changes matter) and this
> path only reads them — one writer, and the read path stays pure.

E4-06's own ticket carries the mirror image of that sentence. Both texts point at
the summary job, and this record does not follow either of them, so it says why
rather than claiming the question was open.

Two further silences are settled with it, because a release cannot be written
without answering them. **What "cumulative comment volume" counts** — every
comment the section holds, or only the comments that survived moderation. And
**what a batch's membership is** — which comments go in, and what happens on a
second run.

**And a third question, which this record did not ask on its first writing and
which E4-04's security review did.** §4 names one trigger — the cumulative
volume — and the first build implemented exactly that. Two findings showed the
sentence does not do what the paragraph it sits in is for:

- **The volume is denominated in the wrong unit.** §4's threshold is "n < 5
  **responses** in a reporting week" — a number of people — and its release
  trigger is a comment volume. §3.2 gives every response two comment items, so
  five comments can come from three students, or from one student across three
  quiet weeks. A release gated on the volume alone goes out over an author set
  far below the number the threshold was chosen to protect, and the batch is what
  is supposed to stand between a released comment and its author.
- **A volume condition stays true once crossed.** The term's cumulative count
  only grows, so every Monday after the first release the same section passes the
  same test and the cutter takes whatever is held — which, after the first sweep,
  is exactly the one week that just closed. That is a per-week batch every week,
  and the instructor's report re-attaches the week for free: the release that was
  not there last Monday came from the week that closed in between. Single-comment
  batches follow in any week where one person wrote something, and a batch of one
  comment carries its own `cut_at`, which is the per-comment timing the batching
  exists to remove.

So the gate settled here is layered, and the departure from §4's literal words is
stated rather than hidden — see the open spec question at the end of this record.

## Decision

**A scheduled task of this ticket's own cuts the batches**, appended to
`app/jobs/tasks.py` as `cut_release_batches` and to `app/jobs/schedules.py` as
`"cut-release-batches-weekly"`, on `crontab(day_of_week="mon", hour="2",
minute="40")`. `app.services.report_comments.cut_due_release_batches` is the one
writer of `release_batch` and `release_batch_member`, and both reads in that
module only read what it wrote.

Monday because SPEC §3.1 closes every window on Sunday at 23:59:59 in the
institution's timezone, so Monday is the first day a week that has just ended has
a final response count — and that count is exactly what decides whether the
week's comments were held. 02:40 because the passes ahead of it settle the data
this one counts: the reclassification sweeps at 00:45 and 01:45 decide which
comments survive §3.3's validity rule, and 02:20 is E3-06's participation sweep.
02:50 is E4-06's summary job, which runs *after* this one and is the only entry
on the schedule that calls a model.

**A comment is held, and so eligible for a batch, when all three of these are
true**: its week's response count is below the threshold, its window has closed,
and it is in no batch already. The second is why an open week is never released
from — a window still taking responses has no final count, so a comment released
from it may belong to a week that reaches the threshold and would then be shown
twice, once under its own week and once in a batch with the week stripped off.
That definition is written once in `app.services.report_comments._held_comments`
and selected from twice, so the set the gate is evaluated over is the set that
goes out; two copies that drifted would gate on one set and release another.

**The gate over that set is three legs, and every one must open.**

- **(a) The cumulative comment-answer volume for the term reaches the
  threshold** — §4's literal trigger, kept. Every comment answer the section
  holds in the term, every week, every moderation state, released or not,
  counted from `report_comment`. §4's phrase is "comment volume", which is a
  statement about how much a section has said rather than about how much survived
  review; a volume computed after moderation would move backwards, so an
  instructor excluding a comment could take a section back under the threshold
  after it had crossed.
- **(b) The distinct people behind the unreleased held comments reach the
  threshold.** This is what §4's threshold actually counts, and it is the leg the
  security round added.
- **(c) Those comments span at least two distinct under-threshold closed weeks.**
  A batch confined to one week is the week attribution
  [0153](0153-a-release-drops-its-week-because-the-gradebook-ledger-would-otherwise-name-the-author.md)
  removes, arriving through the report's week-to-week delta rather than through a
  field.

**Leg (b) subsumes the other two, and all three are written out anyway.** The
respondents behind a held set are at most the number of held comments, which is
at most the cumulative volume, so (b) fails wherever (a) does; and an
under-threshold week holds fewer than `threshold` responses by definition, so a
held set inside one week has fewer than `threshold` respondents and (b) fails
wherever (c) does. **(b) is therefore the effective floor.** Keeping (a) and (c)
as their own named conditions is deliberate: each is a separate reading of §4 that
this build stands on, each survives a change to another's denominator — the day
somebody counts responses instead of respondents, (c) is what still refuses a
one-week batch — and the reviewer this module is written for asked for the
property rather than for an implementation of it. The cost is three conditions
where one would compute the same answer today, and it is worth it.

**When any leg fails, nothing is cut, and that is the stance.** Held is the safe
direction: an under-threshold comment that stays held still feeds the summary
(§4 says so in as many words) and can be released later, while a comment released
early cannot be un-shown — nothing in this schema deletes a membership row
(ADR 0146). The price is named rather than glossed: **a section whose quiet week
never finds a companion keeps those comments held for the rest of the term**, and
a term that ends there ends with them unreleased. That is a real loss to the
students who wrote them, and it is accepted because the alternative loss is a
disclosure that cannot be taken back.

**One batch per crossing, holding the whole held set, in one transaction per
section and term.** The service commits after each pair, so a walk over every
section in the institution keeps the releases it has already cut when a worker
dies on the fifth one.

**A comment released twice is a defect to see.** The held set is chosen by
anti-join against `release_batch_member`, so a second run finds nothing to do;
`answer_id` is unique on that table ([0146](0146-a-release-is-a-batch-row-and-a-membership-row.md))
and nothing in the cutter catches the integrity error a broken held query would
provoke. ADR 0146 left that choice to this ticket and this is it.

**The release is carried by one report, and E4-07 places it.** Released comments
appear in the latest published week's report under a from-earlier-weeks heading,
with no week attribution anywhere —
[0153](0153-a-release-drops-its-week-because-the-gradebook-ledger-would-otherwise-name-the-author.md)
argues that half.

## Alternatives rejected

**The E4-06 summary job cuts the batches — both tickets' own recommendation.**
It is genuinely attractive: that job already runs weekly at the only moment the
volume matters, and one job means one walk over the institution's sections
instead of two. Three costs, and the first is the one that decided it.

*A provider outage would delay a release.* The summary job's whole subject is a
model call, with a sixty-second budget per stream per section and no fail-open
([0148](0148-the-summary-contract-splits-what-the-model-produces-from-what-the-caller-injects.md)).
A release is arithmetic over rows this system already holds; SPEC §4 promises the
comments surface once the volume crosses, and hanging that promise off an
external service means a provider having a bad Monday is a week in which
somebody's held comments do not appear. The two have no reason to fail together
and this keeps them apart.

*It puts §4's suppression rule inside a job about §5.1's summaries.* The whole
argument for `app/services/report_comments.py` existing as a module is that SPEC
§14.3 marks the suppression for line-by-line human review, which is a review of a
file rather than of a paragraph inside somebody else's. A crossing evaluated in
the summary job would be reviewed as part of a diff about prompts.

*And it couples two parallel builds.* E4-04 and E4-06 are built at the same time
off the same head. Putting the writer in E4-06 would make this ticket's whole
release path untestable until that one landed, and would give one job two
tickets' tests.

**The joint per-section transaction both tickets sketched**, in which one pass
generates a section's summary and cuts its release together, is given up with
this alternative, and it is worth naming as a real loss rather than folding it
into the paragraph above. Under one pass a section's Monday work is atomic:
either the week's summary and its release both land or neither does. Under two
tasks a section can have a release with no summary for twenty minutes, or a
summary and no release if the cutter fails. That is accepted because neither is a
correctness state — the summary is per week and the release is per term, nothing
reads one to compute the other, and E4-07 renders whatever is there — while the
coupling it buys is a release that a model timeout can postpone.

**Evaluate the crossing at read time.** The shape E4's breakdown already
rejected, restated because it is what an implementer reaches for when the job
looks like ceremony. A release re-derived on each read changes as data changes,
so a comment can appear and disappear; and the moment it first appears is itself
a timing signal, which is precisely what §4's "batched so that timing cannot
identify an author" removes. It also puts a write on a read path, which is how a
report generated twice cuts two batches.

**Cut on submission — check the crossing whenever a comment is stored.** It is
the most responsive answer and the worst one for §4: the batch would be cut the
instant the threshold-crossing comment arrived, so `cut_at` would date the
release to within seconds of one student's submission. Batching exists to stop
exactly that inference.

**Count volume after moderation** — only comments in a published or kept state.
Defensible, and it reads as the more careful choice: why should a comment an
instructor excluded help release other people's? Rejected on the ratchet. The
volume is a threshold, and a threshold computed over a set that can shrink is one
a section crosses and then un-crosses, which either releases comments that should
not have been released or leaves a batch already cut against a volume that is now
below the line. §4's sentence is about how much a section wrote.

**Count responses rather than comments** *as leg (a)*. §4 says "comment volume"
and the response count is already the *other* number in the same paragraph — the
per-week threshold. Using one number for both rules would make a term of silent
weeks release nothing however many students answered, and would make the
cumulative rule a restatement of the weekly one. What the security round changed
is not this: leg (a) still counts comments, and the count of *people* is a
separate leg beside it rather than a replacement for it.

**Keep §4's single volume trigger and change nothing.** The literal reading, and
what shipped before the security review. It has the strongest claim of any
alternative here — the spec names one trigger, an ADR does not get to overrule
the spec, and every other test in this epic was green against it. It is rejected
on the two findings above: §4's own stated purpose in the same sentence is that
the release is "batched so that timing cannot identify an author", and a per-week
batch of one person's comments satisfies the sentence while defeating the purpose
written beside it. Where a spec sentence and the goal it states come apart, the
conservative side is the one to hold while the owner rules, and this record says
so out loud rather than quietly implementing a spec it is not following.

**Count distinct responses rather than distinct respondents in leg (b).** One
join shorter, and it never reaches `response.user_id` at all — genuinely
attractive in a module whose whole subject is not naming people. Rejected because
the two numbers come apart exactly where the finding lives: §3.2 gives one
response two comment items, so one student answering both is two comments and one
response — but a student who answers in three quiet weeks is three responses and
one person, and a response count would release that as though three people had
written. §4's threshold is a number of people, so the leg has to count people.
What the module owes in exchange is that the column is used only to count: it is
grouped and `count(distinct …)`-ed inside one query, is not selected by the
membership read, and reaches no return value.

**A larger span than two weeks for leg (c)** — three, or "half the term's quiet
weeks". Strictly safer, and unbounded in cost: each extra week required is
another stretch of term a section's comments spend held. Two is the smallest
number that makes the report's week-to-week delta ambiguous, which is a floor
with a reason; three would be a number with a feeling.

**Cut the gate but bound the wait — release a lone quiet week after N Mondays.**
It closes the withholding cost named in the decision, and it reintroduces the
defect through the calendar: a batch that goes out because a timer expired is a
batch whose `cut_at` dates the week it came from as precisely as a per-week batch
does. If the wait is ever judged unacceptable, the thing to change is what the
gate counts, not to add a bypass around it.

**Catch the integrity error and treat a double release as a no-op.** It would
make the cutter robust against its own held query being wrong, which is the
problem: a second membership can only arise from an anti-join that is broken, and
a broken anti-join is a bug about which comments are released. Swallowing it
turns a wrong release into a silent one.

**A batch per week rather than per crossing.** It preserves more information and
gives every released comment a `cut_at` that dates its week's release — the
per-comment timing the batching exists to remove, one level up. ADR 0146 makes
the same argument about a unique constraint over `batch_id`.

## Consequences

- **The beat schedule holds two weekly Monday entries and then a third**: the
  participation sweep at 02:20, this cut at 02:40, and E4-06's summary at 02:50.
  The ordering is load-bearing in one direction only — this pass must run after
  the reclassification sweeps — and the summary job does not read the release, so
  a Monday on which the cut fails still produces summaries.
- **A section's first release can only happen on a Monday**, so a section that
  crosses on a Tuesday waits six days. That is a cost paid deliberately: it is
  also what makes `cut_at` say nothing about when any comment arrived, because
  every batch in the institution is dated to the same handful of minutes.
- **Nothing un-releases.** ADR 0146 already says a released comment is a row and
  nothing deletes one; this record adds that no state or reversing row is decided
  here either. A release cut against a volume somebody later disputes is a
  conversation, not a rollback.
- **The read path holds no threshold for the release.** `released_comments`
  applies no rule of its own — the batch *is* the decision — so a widening there
  would have to be a widening of the cutter, which is one file and one weekly
  writer.
- **The joint transaction is gone and E4-06 does not get it back cheaply.** If a
  later ticket wants a section's Monday work atomic, this is the decision to
  revisit, and the thing that would have to change first is the summary job's
  dependence on a provider.
- **`cut_due_release_batches` commits, which is unusual for a service here.** Two
  of six beat tasks now leave the commit to the service they call, each for its
  own reason, and `app/jobs/tasks.py`'s module docstring names both rather than
  claiming one shape.
- **A section's quiet comments can stay held to the end of a term**, and this is
  the price of the fail-closed stance falling on the students who wrote them. A
  section that crosses once and then has a single quiet week for the rest of the
  term never releases that week, because one week satisfies neither leg (b) nor
  leg (c). §4's "they surface as raw text" is not honoured for those comments.
  They still feed the summary, which is the other half of §4's own sentence, so
  the signal reaches the instructor even where the text does not.
- **This module now reaches `response.user_id`, in exactly one place.** Leg (b) is
  a count of people, so the held-comment definition walks `answer.response_id`
  and then `response.user_id`. The column is grouped and counted and never
  selected into anything a caller sees, and the service's own docstring points a
  reviewer at the three functions that have to be checked rather than at the
  whole file. It is a real widening of what this module can reach, recorded here
  for that reason.
- **A release can no longer be planted by planting comments alone.** Any world
  that expects a batch now needs a threshold's worth of distinct respondents
  across two closed under-threshold weeks, which is a larger world than the first
  build's tests needed. A later ticket writing a release case meets that shape.

## Open spec question — the owner's to settle

**This gate is a reading of SPEC §4 rather than §4's own words, and the record
says so plainly rather than letting an ADR stand in for a spec edit.** §4 names
one trigger: "they surface as raw text once the section's cumulative comment
volume for the term crosses the threshold". Legs (b) and (c) are not in it.

The case for them is that §4's stated purpose in the same sentence — "batched so
that timing cannot identify an author" — is not achieved by the trigger it names,
for the two reasons in this record's context. The case against is that a spec
sentence is a spec sentence, and `docs/adr/README.md` is explicit that a decision
contradicting the spec is not an ADR's to make.

**This build holds the conservative side while the question is open.** It
releases strictly less than §4's literal trigger would and never more, so nothing
here shows an instructor a comment the spec's own words would have withheld, and
the cost is the withholding named above. **No spec edit rides in this pull
request.** What the owner has to settle is whether §4's sentence is amended to say
what the threshold protects — people, across more than one week — or whether the
literal trigger stands and the withholding is the wrong trade. Either answer is a
short change to §4 and a change to this record; neither is the implementer's to
make.
