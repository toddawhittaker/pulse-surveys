# 0182 — Raw comments are held per stream by distinct commenters, and a released comment never returns to its week

Amends [0152](0152-the-crossing-is-cut-by-a-task-of-its-own-not-at-read-time-and-not-by-the-summary-job.md)
(what "held" means, and its claim that leg (b) subsumes leg (c)) and corrects
[0153](0153-a-release-drops-its-week-because-the-gradebook-ledger-would-otherwise-name-the-author.md)'s
floor sentence. Ticket E5.1-01.

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

**Leg (c) is load-bearing now.** Held per stream, one week can supply two held
streams with up to twice `threshold - 1` distinct authors, so leg (b) can open on
one week alone. Only leg (c), at least two distinct `week_id`s (weeks, not
stream-weeks), refuses that batch, which the report's week-to-week delta would
date (0153).

## Alternatives rejected

- **Count responses.** The defect itself (entry 50).
- **Count comment answers.** Inside one stream-week this equals the people today,
  because a student holds one response a week and a response one answer per
  question. It stops being equal the day either uniqueness relaxes, and the
  threshold protects people, so it counts people.
- **Count released authors too.** Their comments are already shown with no week,
  and counting them lets a lowered threshold re-show them under it.
- **One notice per week.** It claims both groups are held when one is shown.
- **Show the empty-week line for a stream nobody commented in.** It tells a
  reader zero apart from one to four.

## Consequences

- §5.1's "empty groups show a one-line notice" is met on the instructor report
  by the suppression notice: a shown stream always has comments.
- Raising the threshold does not re-hold a stream already shown. That is carried
  to E11 (hand-off 3, written by E5.1-09).
- The design mockups above still show the old placement and sentence; they are
  for the design owner to update.
- `_held_comments` and `_commenters_by_stream_week` both reach
  `response.user_id`, each only to count.
