# 0182 — Raw comments are held per stream by distinct commenters, and a released comment never returns to its week

Amends [0152](0152-the-crossing-is-cut-by-a-task-of-its-own-not-at-read-time-and-not-by-the-summary-job.md)
(what "held" means, and that the gate's legs count per stream) and corrects
[0153](0153-a-release-drops-its-week-because-the-gradebook-ledger-would-otherwise-name-the-author.md)'s
floor sentence. Ticket E5.1-01.

**Status:** Accepted
**Date:** 2026-10-03
**Ticket:** [E5.1-01](../tickets/e5.1/E5.1-01-commenter-threshold.md)

## Context

SPEC §4 now counts the n-threshold in distinct students commenting in one stream
in one reporting week, and says a released comment is never shown again under
its week; §4.1 item 3 says the same. Before this, the gate counted the week's
responses. In a week of six respondents where one student wrote about the
instructor, that one comment was shown, and the per-week completion ledger in the
gradebook ([0125](0125-the-score-comments-per-week-ledger-is-instructor-visible.md))
could name its author. That is `docs/MISTAKES.md` entry 50: a threshold that
protects people was crossed by a count of something else.

The spec settles the unit. It does not settle five construction questions this
record answers: whether released comments count toward their week, what an empty
stream shows, where the notice goes and what it says, which count chooses the
summary's mode, and what happens to the release gate's legs.

## Decision

**One count, one definition.** `app.services.report_comments.stream_is_suppressed`
is true when fewer than `n_threshold()` distinct `response.user_id` hold a comment
in that section, week and stream. It reads one private subquery,
`_commenters_by_stream_week`; `_held_comments` joins the same subquery. Moderation
state does not matter: a flagged or excluded comment still has an author.

**Released comments do not count, and are never returned under their week.** The
count leaves out comments with a `release_batch_member` row, and `visible_comments`
anti-joins that table as well. The two halves cover different failures: without
the anti-join, a late comment that lifts a stream over the line would bring the
released ones back with it; without the exclusion from the count, lowering the
setting from 5 to 4 would show a stream whose four authors are already in a batch.

**An empty stream is suppressed.** Zero is below any threshold, so a stream nobody
commented in shows the same notice as a thin one. A reader cannot tell nobody
from one person.

**The notice is per stream and states no count.** `small_n` moves from the report
onto each stream (`suppressed`, `threshold`), and each suppressed comment group
shows the notice inside itself, after its summary. A week with both streams held
shows two. The notice states the threshold and nothing counted: inside one group,
any count reads as that group's. This departs from
`design/InstructorMondayReport.dc.html:69-73`, which places one notice under both
groups, and from `design/SmallNNotice.dc.html:31-33`, whose sentence leads with
"Only N of M students have responded".

**The summary's mode follows the stream.** `_summary_row` asks
`stream_is_suppressed`, so a thin instructor stream in a full week is written in
small-N mode and passes the reuse guard. The row's `response_count` stays the
week's responses (§5.1, [0148](0148-the-summary-contract-splits-what-the-model-produces-from-what-the-caller-injects.md)).

**The release gate's legs count per stream.** A released card carries its stream
chip, and each week's report says which streams were held. Pooled across streams,
a week whose course stream was held at four authors and a week whose instructor
stream was held at one opened the gate together, and the batch's one instructor
card was that week's lone commenter. So volume, distinct authors and distinct
weeks are each counted per (section, term, stream). A run writes at most one
batch per section and term, holding exactly the streams whose three legs opened;
another stream stays held. Each stream's slice of a release then stands on at
least a threshold's worth of its own authors over at least two of its own weeks.
Per stream, leg (b) again subsumes leg (c), since one stream's held set inside one
week is below the threshold by definition. 0153's third narrowing — a release
partitioned by stream — is closed for this design rather than reopened: each part
meets the floor, so the per-card chip stays.

## Alternatives rejected

- **Count responses.** The defect itself (entry 50).
- **Count comment answers.** Inside one stream-week this equals the people today,
  because a student holds one response a week and a response one answer per
  question. It stops being equal the day either uniqueness relaxes, and the
  threshold protects people, so it counts people.
- **Count released authors too.** Their comments are already shown with no week,
  and counting them lets a lowered threshold re-show them under it.
- **Pool the streams in the gate.** The finding above.
- **One notice per week.** It claims both groups are held when one is shown.
- **Show the empty-week line for a stream nobody commented in.** It tells a
  reader zero apart from one to four.

## Consequences

- §5.1's "empty groups show a one-line notice" is met on the instructor report
  by the suppression notice: a shown stream always has comments.
- Raising the threshold re-holds a stream already shown. The hold compares each
  stream-week's commenters with the threshold in force at the time of the read
  (`backend/app/services/report_comments.py:850`), so a changed
  `N_THRESHOLD_DEFAULT`, or a web and a worker process running with different
  values, hides comments the instructor has already read and can put them in a
  batch. That is carried to E11 (hand-off 3 in
  `docs/tickets/e6/carried-from-e5.md`).
- Summaries stored before E5.1 are not regenerated, so a thin stream in a full
  week may keep a summary written in ordinary mode.
- The small-N prompt (`backend/app/ai/prompts/summary.v2.md:41-48`) says "fewer
  students answered this week", which is a false premise for a thin stream in a
  well-answered week. This and the point above are carried to E6.
- The design mockups above still show the old placement and sentence; they are
  for the design owner to update.
- `_held_comments` and `_commenters_by_stream_week` both reach
  `response.user_id`, each only to count.

## Amendment, 2026-10-03 (E5.1-12)

The count above counts only comments holding a character Python's `str.strip()`
would keep: v001's one-argument `btrim` trimmed only spaces and let a comment of
tabs and line breaks count its author, v002 (revision `c8b7f89fc195`) used a
`[:space:]` class that still followed the collation, and v003 (revision
`ad9da2d96664`) lists the code points `strip` removes and names no class, so
the rule is the same under every collation (`docs/disputes/E5.1-12-01.md`).
