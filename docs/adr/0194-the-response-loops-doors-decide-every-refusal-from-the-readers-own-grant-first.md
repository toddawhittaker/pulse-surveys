# 0194 — The response loop's doors decide every refusal from the reader's own grant first

**Status:** Accepted
**Date:** 2026-10-11
**Ticket:** [E7-03](../tickets/e7/E7-03-publish-policy-on-behalf.md)

## Context

E7-01 and E7-02 built the response records, the name channel, the hold and its
two writers, and left who may write to the doors in front of them. E7-04 built
the draft and the check over a gather whose on-behalf half it refused. The
behaviour is settled by SPEC §5.3 and the E7 rulings (`../tickets/e7/README.md`,
rulings 1 to 3, 5, 9 and 10). This record holds the construction choices the
spec leaves open.

## Decision

**The instructor's publish and edit sit behind the report's own gate**
(`reporting._published_section_week`), so they refuse exactly what the report
refuses, with its 404s. A publish when the week has a response, whoever wrote
it, is one 409; an edit with no response yet and an edit by anyone but the first
publisher share another 409 and one sentence, so the refusal never says who
published. Text is bounded and refused, never trimmed (`ResponseWrite`).

**The policy read lists the reader's `lead_review_courses`** (settable) and, for
a chair, the department's led courses (`authz.chaired_courses_with_a_lead`, read
only). `mode` is each course's latest row now. `set_by_role` is carried only on a
course the reader cannot set, so a lead's read never moves with a sibling's
change. A switch calls `record_policy` once per role the reader holds a course of
the prefix under, so a lead who chairs writes one row of each role. A prefix where
the reader sets nothing, and a prefix that does not exist, are one 404.

**The clocks** are `is_owed` and `on_behalf_open` in `services/response_loop.py`,
over one set-based read (`_week_clocks`): the windows, the courses' policy rows
and the answered section-weeks, one query each. The policy of record is
`policy_of_record`'s rule applied to rows read once. The responses-owed read is
the same read over the reader's courses, less the sections they teach or taught.

**Every on-behalf door passes one gate**, in this order: the section is in a
course `lead_review_courses` gives the reader (one query, so a sibling's section
and a key nothing holds fail alike, before the week is read); it is not a section
the reader teaches or taught; the week's report has opened; then either the week
is open on behalf (required, unanswered, +96h) or, for the edit, the reader first
published its response. Every refusal is one exception and one 404. The writer
role is what `lead_review_courses` gives the reader for the course.

**The on-behalf read and gather leave out a summary written before the week's
latest removal**: a row whose `generated_at` is not strictly later than the
latest *decided* `moderation_state` row in the section-week whose state is one
the summary walk leaves out (`HELD_MODERATION_STATES`: an exclusion, or the undo
of a keep). The instant is read by `report_comments.latest_decision_into`,
because that module is the one reader of `moderation_state`. The read carries no
comment, and each stream's `response_count` is the week's response count.

## Alternatives rejected

- **One parameterized door for the instructor and the lead.** Their gates differ
  (teaching grant against leadership grant less taught sections), and SPEC §8's
  reasoning keeps such reads apart.
- **A 403 for a reader with no course** (as the review queue answers). A chair of
  a department with no courses is a real reader; an empty read answers them, and
  the assistant dean, dean and vice president read nothing until E9.
- **Per-section calls for the owed read.** One query per section and week grows
  with the reader's courses.
- **Reading each comment's current state for the filter.** It cannot say when a
  comment left the shown set, which is the comparison; the decision rows can.
- **Counting the routing definer's flags as removals.** A comment starts flagged;
  it never left a shown set.

## Consequences

- Two publishes racing for one empty week can both pass the check; the guard
  trigger refuses a second author, and the same author's second row reads as an
  edit.
- An exclusion later undone still withholds a summary written before it, from
  the on-behalf reader only.
- The instructor's GET of the week's response (decision 1) waits on dispute
  `E7-03-02`; the service behind it is built. The two leadership refusals are
  filed under a new `leadership_response.` copy prefix, whose row in the copy
  governance map is dispute `E7-03-03`.
