# 0193 — The hold reads a per-course policy row, in force at the week's report opening

**Status:** Accepted
**Date:** 2026-10-11
**Ticket:** [E7-02](../tickets/e7/E7-02-the-hold.md)

## Context

SPEC §5.3 lets a lead require a response, and required mode holds the students'
week until a named person publishes one. The owner's rulings for E7
(`../tickets/e7/README.md`) settle the behaviour: a policy covers only its
setter's own courses in a prefix (ruling 1); the first response releases the
week, and an edit never holds it again (ruling 3); a chair acts as lead for a
course with no lead (ruling 5); and the policy in force when a week's report
opens governs that week, so a later change, including a change of lead, never
releases a held week or holds a shown one (ruling 6).

[ADR 0192](0192-the-response-records-are-append-only-and-keyed-by-role.md) keyed
a policy row by prefix, person and role, which leaves the gate to work out which
person was responsible for a course when the week's report opened. Lead mappings
keep no history (`lead_faculty_mapping` holds the current lead only), so that
question cannot be answered about a past moment.

## Decision

**A policy row covers one course, fixed when it is written.** E7-02's migration
(`7f679faf4b8d`) adds `response_policy.course_id`, `NOT NULL`, with the composite
key `(course_id, prefix_id) → course (id, prefix_id)` (`RESTRICT`), so the course
is always in the row's prefix. `course` gains the unique pair `(id, prefix_id)`
for the key to reference. The index is `(course_id, sequence)`. `pulse_app`'s
column `INSERT` gains `course_id`. The guard trigger
(`backend/app/views_sql/response_loop_guard_v002.sql`) now checks the setter
against the row's course: as `LEAD_FACULTY`, the assignment and the mapping for
that course; as `CHAIR`, the chair of its department where nobody leads it.

**A switch is one row per course.** `services/response_loop.record_policy` writes
a setter's switch for a prefix as one row for each course
`authz.lead_review_courses` gives them there under the role they set it as, all
with one `set_at` from `services/clock.now`, in the caller's transaction.

**The policy of record** for a section-week is the latest row by `sequence` for
the section's course with `set_at` at or before the week's report opening
(`reporting.report_opens_at`, [ADR 0184](0184-a-weeks-report-opens-at-six-on-the-monday-after-it-closes.md)).
With no such row, the week is encouraged. Nothing about who leads the course
now is read.

**The states.** `awaiting` when the policy of record is required and there is no
response; `unanswered` when it is encouraged and there is none; `on-behalf` when
the first row by `sequence` was written as `LEAD_FACULTY` or `CHAIR`; `published`
otherwise. The first row decides, so an edit never changes the release. Students
read the latest row's text and time, under the first row's author and role (the
same person, since only the first author may edit).

**Two student results routes.** `GET /student/sections/{section_id}/weeks/{course_week}/results`
answers one week, and `GET /student/sections/{section_id}/results` answers the
latest published week, which is where the student's page opens. Both find the
section among the student's live enrollments and the week among the section's
published weeks before reading any response. Both carry `published_weeks`, the
section's course weeks whose report has opened, ascending, so the page pages back
through published weeks only (SPEC §5.4). Every refusal on either route is one 404
with one sentence, a section with no published week included.

## Alternatives rejected

- **Resolve the responsible person at read time** from today's mapping. A lead
  change after the opening would then move the week to the new person's switch,
  which ruling 6 forbids.
- **A history table for lead mappings.** It answers the question in general, but
  it is a second record of the org structure that the LMS owns, kept for one
  reader.
- **Keep the prefix-keyed row and snapshot the policy per section-week when the
  report opens.** That needs a job that writes at 06:00 every Monday, and a week
  read before the job ran would have no answer.
- **The course-in-prefix rule as a check in the trigger.** A composite key states
  it in the schema, the device `comparison_set_member` already uses for level.

## Consequences

- ADR 0192's "a policy is keyed by prefix, person and role" and its policy index
  are superseded by this record. The row still names the prefix, the person and
  the role, because that is what the setter did.
- A switch for a prefix does not reach a course the setter starts leading later.
  The new lead sets that course's policy.
- E7-03 adds the policy routes in front of `record_policy`, and the publish and
  edit routes in front of `publish_response`. Both writers decide nothing about
  who may write; the doors and the guard trigger do.
- The migration's downgrade refuses while `response_policy` holds a row.
- **A known edge, for review.** The author's name comes through the staff-name
  definer, which judges the student's enrollment on the UTC date of the database clock
  ([ADR 0191](0191-a-staff-name-reaches-a-reader-through-one-definer.md)), while
  the route judges it on the institution's date from `services/clock`. Near
  midnight the two can disagree, and a live student whose enrollment starts or
  ends that day can then reach a released week whose author the definer does not
  answer. The read raises in that case (a 500) rather than serving the response
  without its author. Kept simple on purpose; a role-only attribution is the
  alternative if it shows up in practice.
