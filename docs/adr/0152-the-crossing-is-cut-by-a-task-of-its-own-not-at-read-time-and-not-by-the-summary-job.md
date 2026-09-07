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

**Volume is every comment answer the section holds in the term** — every week,
every moderation state, released or not — counted from `report_comment`, which
is comment-kind answers carrying non-empty text. §4's phrase is "comment volume",
which is a statement about how much a section has said rather than about how much
survived review. A volume computed after moderation would also move backwards: an
instructor excluding a comment could take a section back under the threshold
after it had crossed, and a release cut on a number that then changed is a
release nobody can explain.

**A comment is held, and so eligible for a batch, when all three of these are
true**: its week's response count is below the threshold, its window has closed,
and it is in no batch already. The second is why an open week is never released
from — a window still taking responses has no final count, so a comment released
from it may belong to a week that reaches the threshold and would then be shown
twice, once under its own week and once in a batch with the week stripped off.

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

**Count responses rather than comments.** §4 says "comment volume" and the
response count is already the *other* number in the same paragraph — the per-week
threshold. Using one number for both rules would make a term of silent weeks
release nothing however many students answered, and would make the cumulative
rule a restatement of the weekly one.

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
