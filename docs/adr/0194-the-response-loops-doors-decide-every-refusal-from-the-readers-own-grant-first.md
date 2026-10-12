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

**The instructor's read, publish and edit sit behind the report's own gate**
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
  the assistant dean, dean and vice president read nothing here (ADR 0206 later
  gave them the exclusion log and policy over their purview).
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
  the on-behalf reader and, since E7-10, from every draft and check
  ([ADR 0195](0195-the-draft-and-the-check-read-stored-summaries-and-refuse-what-students-may-not-read.md)).
- The two leadership refusals are filed under their own `leadership_response.`
  copy prefix, a surface of its own in the copy governance map (ruling on
  `E7-03-03`), not under the moderation screen's.

**Amended by E7-10 (the boundary review's fixes).** The gate's last step has a
third purpose, the read. The on-behalf read admits a week that is open on behalf,
as before, or a week whose first response the reader published, so the first
publisher can come back to edit it. Its payload gains `response`: null while
the week is unanswered, and the week's `WeekResponseView` for that first
publisher. Every other reader of an answered week, the course's own lead
included when the instructor answered, still gets the one 404.
`WeekResponseView` carries `can_edit`, true exactly when the reader first
published the week's response, on the instructor's routes and the on-behalf
ones alike; the composer offers Edit only then.

*Amended by [0206](0206-the-drill-down-reuses-the-report-read-only-and-the-wider-roles-read-the-log-and-policy.md):* the policy read lists every course of an assistant dean's, dean's or vice president's purview, which they read and do not set; the on-behalf doors keep their one 404 for them, and the summary filter compares decision sequences rather than instants.
