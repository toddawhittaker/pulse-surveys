# 0190 — A lead reviews flagged text at any threshold, through a door of its own, and the log withholds held text

**Status:** Accepted, amending [0189](0189-an-instructor-decides-only-on-a-comment-their-report-returns.md) (the shared write's parameters)
**Date:** 2026-10-10
**Ticket:** [E6-05](../tickets/e6/E6-05-review-queue-and-exclusion-log.md)

## Context

SPEC §5.2 routes abuse of the instructor to the course's Lead Faculty review
queue and keeps an exclusion log for leadership. Ruling 1 lets the lead see a
harmful comment's text and section below the threshold, with no week or time;
§5.5 otherwise shows raw comments up-chain only where the threshold is met. The
spec does not say whose grant a queue or log is read over, how the lead's door
relates to the instructor's, or what the log may quote.

## Decision

**Who reviews what.** `authz.lead_review_courses` answers, per course, the one
role covering it: `LEAD_FACULTY` for the courses a person leads (from the
mapping, and only with a `LEAD_FACULTY` assignment), `CHAIR` for the courses of
a chaired department that nobody leads. Instructor grants are never unioned in,
so a lead who also teaches a sibling section does not reach it (SPEC §4.1 item
2). **And the queue leaves out every section the reader teaches** (ruling 7,
from this ticket's review): a lead or chair who also holds an instructor
assignment on a section of a reviewed course would otherwise read that
section's held text here, which the instructor door refuses them. The first
draft of this record considered only the sibling-section case and missed the
own-section one. The exclusion is by section (`authz.taught_section_ids`, the
instructor door's own source), so the course's other sections stay in the
queue, and the leader door, which reads the same select, refuses such a comment
with the queue's 404. Every other role answers nothing and is refused with a 403: an assistant
dean until E9's supervision walk ([0108](0108-the-leadership-limb-is-scoped-by-the-launchers-own-grant.md)),
and a dean or vice president, whom §5.2 does not name as a reviewer.

**The queue** is the comments of those courses read from `report_comment` v004
that hold a harmful verdict and whose latest state is still `FLAGGED_COLLAPSED`
(`report_comments.reported_status_of`). v004 is the one place the Care-class
exclusion lives, so a comment ever verdicted threat or self-harm is absent even
after a later harmful verdict; `pulse_app` gains no grant. An item is the answer
id, the text and the section label, shuffled on every read from the operating
system's source.

**Each door holds its own check.** `decide_as_leader` takes the comment's lock,
re-runs the queue's own select for that answer id, and only then calls the
shared write with the covering role. The instructor's door is untouched, so a
held comment is still refused to its instructor and accepted from its lead.
Anything not in the reader's queue now (a sibling's comment, a comment of a
section the reader teaches, a decided or Care-class one, an id nothing holds) is one 404 with one sentence. A lead has
no undo, and the reason is optional (every queued comment was AI-flagged) with
the instructor's bounds. *Amending 0189:* the shared write now takes the
comment's key and flag class rather than an instructor card.

**The log** lists every row with a decider in state `EXCLUDED` or `KEPT` inside
the reader's courses, through v004, newest first by `sequence`: the section
label, the direction (`decision`, the stored `EXCLUDED` or `KEPT`, so the log
shows both directions as SPEC §5.2 asks), the stored role, whether the AI flagged the comment, the reason, the date
in the institution's zone, and an excerpt of 140 characters. **The excerpt is
null unless the comment's own report shows it under its week**
(`visible_cards` for its section, week and stream). That withholds held text,
text of a week not yet fully moderated, and released text: a decision date
beside a released comment would give back the week a release drops
([0153](0153-a-release-drops-its-week-because-the-gradebook-ledger-would-otherwise-name-the-author.md)).

**The de-anonymization statement for leadership views** (read against 0153,
[0162](0162-the-small-n-summary-is-a-second-live-prompt-version-and-a-store-time-guard.md),
[0178](0178-a-published-benchmark-week-is-frozen-at-the-earliest-close-in-its-population.md)
and [0179](0179-a-benchmark-figure-is-sealed-against-what-its-reader-can-subtract.md)).
A queue item places a comment among one section's students, the set its
instructor's report already places it in, and carries no week, instant, author
or count. A log row with held text carries no text. **Two residuals are
accepted, not closed.** First, the queue's contents change over time: a reader
who looks every hour learns when a comment arrived, and arrival follows a
window's close, so that says the week, and a reader who can also open the
section's per-week completion ledger in the gradebook (§3.4) can narrow the
author in a small week. Ruling 1 accepts showing the
text, and the shuffle removes order as a second clock. Second, a lead's own
stated reason is free text shown beside a date, and could quote a held comment.

## Alternatives rejected

- **The Care rule rebuilt in Python, or a grant on `answer`.** A second copy
  that disagrees on a threat-then-harmful comment.
- **`resolve_scope`, or a chair's whole department.** The first unions
  instructor grants in; the second gives a led course two reviewers.
- **A role flag on the shared write.** One door's check could then loosen the
  other's.
- **A 403 for a sibling's or decided comment.** Says the comment exists.
- **An excerpt for released comments.** Re-attaches the week.

## Consequences

- An assistant dean, a dean and a vice president read no queue and no log
  until E9 decides what their purview reaches here.
- Disputes `../disputes/E6-05-01.md` to `-04.md` are ruled: the lock test was
  rewritten so it can fail, the copy surface `leadership_moderation.` is
  governed, the log row gained `decision` (seven members, not the work order's
  six), and the two route inventories now expect a CSRF member per decision
  door and the moderation routes beside the named sets.
